const { DynamoDBClient, GetItemCommand, UpdateItemCommand } = require('@aws-sdk/client-dynamodb');
const Memcached = require('memcached');
const axios = require('axios');
const crypto = require('crypto');
const pipeline = require('util').promisify(require('stream').pipeline);
const { PassThrough, Readable, Writable } = require('stream');
const { log } = require('console');

const cacheEndpoint = process.env.ELASTICACHE || '';
const cachePort = 11211;
const memcachedClient = cacheEndpoint != '' ? new Memcached(`${cacheEndpoint}:${cachePort}`) : null;
const TTL = 60 * 60 * 24; // 1 day
const ddbClient = new DynamoDBClient();

const prices = {
    'gpt-3.5-turbo': [0.0015, 0.002],
    'gpt-3.5-turbo-16k': [0.003, 0.004],
    'gpt-3.5-turbo-instruct': [0.0015, 0.002],
    'gpt-4': [0.03, 0.06],
    'gpt-4-32k': [0.06, 0.12],
};

function calculateCost(model, inputTokens, outputTokens) {
    let price = prices[model] || [0, 0];
    return price[0] * inputTokens / 1000 + price[1] * outputTokens / 1000;
}

async function getUsageAndLimit(compositeKey) {
    let today = new Date();
    let currentMonth = (today.getMonth() + 1).toString().padStart(2, '0') + today.getFullYear().toString().slice(2, 4);

    let params = {
        TableName: 'openai-usage',
        Key: {
            'composite_key': {
                'S': compositeKey
            }
        },
    };

    const command = new GetItemCommand(params);
    const response = await ddbClient.send(command);
    let item = response.Item;
    return {
        usage: item && item[currentMonth] ? Number(item[currentMonth].N) : 0,
        limit: item && item.limit ? Number(item.limit.N) : null
    };
}

async function updateUsage(user, project, model, staging, cost) {
    let today = new Date();
    let currentMonth = (today.getMonth() + 1).toString().padStart(2, '0') + today.getFullYear().toString().slice(2, 4);
    let compositeKey = `${user}#${project}#${model}#${staging}`;

    let params = {
        TableName: 'openai-usage',
        Key: {
            'composite_key': {
                'S': compositeKey
            }
        },
        UpdateExpression: 'SET #month = if_not_exists(#month, :zero) + :cost, ' +
            '#user = :user, #project = :project, #model = :model, #staging = :staging',
        ExpressionAttributeValues: {
            ':zero': {
                'N': '0',
            },
            ':cost': {
                'N': String(cost)
            },
            ':user': {
                'S': user,
            },
            ':project': {
                'S': project,
            },
            ':model': {
                'S': model,
            },
            ':staging': {
                'S': staging,
            },
        },
        ExpressionAttributeNames: {
            '#month': currentMonth,
            '#user': 'user',
            '#project': 'project',
            '#model': 'model',
            '#staging': 'staging',
        }
    };

    const command = new UpdateItemCommand(params);
    await ddbClient.send(command);
}

if (typeof awslambda === 'undefined') { // stub for testing
    global.awslambda = {
        streamifyResponse(lambdaHandler) {
            return async (event, context) => {
                responseStream = Writable();
                responseStream._write = (chunk, encoding, callback) => {
                    console.log(chunk.toString());
                    callback();
                }
                await lambdaHandler(event, responseStream, context);
            };
        }
    }
}

class BufferStream extends PassThrough {
    constructor(options) {
        super(options);
        this._buffer = [];
    }

    _write(chunk, encoding, callback) {
        super._write(chunk, encoding, callback);
        this._buffer.push(chunk);
    }

    getBuffer() {
        return Buffer.concat(this._buffer);
    }
}

exports.lambdaHandler = awslambda.streamifyResponse(async (event, responseStream, context) => {
    const headers = {
        'content-type': 'application/json',
        'authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        'openai-organization': process.env.OPENAI_ORGANIZATION,
    };
    // if (context.headers['openai-model']) {
    //     headers['openai-model'] = context.headers['openai-model'];
    // }
    const body = JSON.parse(event.body);
    // let model = headers['openai-model'] || JSON.parse(body).model;
    let model = body.model;
    if (!prices[model]) {
        model = model.substring(0, model.lastIndexOf('-'));
    }
    const user = 'fulano';
    const project = 'hello';
    const staging = context.functionName.split('-').pop();
    let url = 'https://api.openai.com/v1' + event.rawPath;
    if (event.rawQueryString && event.rawQueryString != '') {
        url = url + '?' + event.rawQueryString;
    }

    let key, result;
    if (memcachedClient && !event.nocache) {
        key = crypto.createHash('sha256').update(event.body).digest('hex');
        console.log('Cache key: ' + key)
        result = await new Promise(resolve => memcachedClient.get(key, (err, data) => {
            if (err) throw err;
            resolve(data)
        }));
        if (result) {
            console.log('Cache hit');
            await pipeline(
                Readable.from(Buffer.from(result)),
                responseStream,
            );
            return;
        }
    }

    let { usage: projectUsage, limit: projectLimit } = await getUsageAndLimit(`*#${project}#*#${staging}`);
    if (projectLimit !== null && projectUsage >= projectLimit) {
        throw new Error(`Project ${project} usage limit exceeded`);
    }
    let { usage: modelUsage, limit: modelLimit } = await getUsageAndLimit(`*#${project}#${model}#${staging}`);
    if (modelLimit !== null && modelUsage >= modelLimit) {
        throw new Error(`Project ${project} usage limit exceeded for model ${model}`);
    }
    if (projectLimit === null && modelLimit === null) {
        throw new Error(`Project ${project} must have a usage limit`);
    }
    let { usage: userUsage, limit: userLimit } = await getUsageAndLimit(`${user}#${project}#${model}#${staging}`);
    if (userLimit !== null && userUsage >= userLimit) {
        throw new Error(`User ${user} usage limit exceeded for project ${project} and model ${model}`);
    }

    const httpResult = await axios({
        method: 'POST',
        url: url,
        data: event.body,
        headers: headers,
        responseType: 'stream',
    });

    bufferStream = new BufferStream();
    await pipeline(
        httpResult.data,
        bufferStream,
        responseStream,
    );

    const buffer = bufferStream.getBuffer().toString();
    if (!body.stream) {
        const response = JSON.parse(buffer);
        if (!response.error) {
            const cost = calculateCost(
                model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            );
            await updateUsage(user, project, model, staging, cost);
            await updateUsage('*', project, model, staging, cost);
            await updateUsage('*', project, '*', staging, cost);
        }
    } // TODO: calculate usage for streamed responses

    if (memcachedClient && !event.nocache) {
        await new Promise((resolve, reject) => memcachedClient.set(key, buffer, TTL, (err) => {
            if (err) {
                reject(err);
            } else {
                log('Cached');
                resolve();
            }
        }));
    }
});

if (require.main === module) { // for testing
    const event = {
        rawPath: '/chat/completions',
        body: JSON.stringify({
            messages: [
                { role: 'user', content: 'Tell me a story in 100 words' }
            ],
            model: 'gpt-3.5-turbo-0613',
            stream: true,
        }),
    };
    const context = {
        functionName: 'openai-proxy-dev',
    };

    exports.lambdaHandler(event, context)
        .then()
        .catch(error => console.error(error));
}
