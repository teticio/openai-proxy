if (typeof (awslambda) === 'undefined') {
    // For testing
    global.awslambda = require('./awslambda');
}
const { DynamoDBClient, GetItemCommand, UpdateItemCommand } = require('@aws-sdk/client-dynamodb');
const Memcached = require('memcached');
const axios = require('axios');
const crypto = require('crypto');
const pipeline = require('util').promisify(require('stream').pipeline);
const { PassThrough } = require('stream');
const { prices } = require('./prices');

const cacheEndpoint = process.env.ELASTICACHE || '';
const cachePort = 11211;
const memcachedClient = cacheEndpoint != '' ? new Memcached(`${cacheEndpoint}:${cachePort}`) : null;
const TTL = 60 * 60 * 24; // 1 day
const ddbClient = new DynamoDBClient();

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
                'S': compositeKey,
            }
        },
        UpdateExpression: 'SET #month = if_not_exists(#month, :zero) + :cost, ' +
            '#user = :user, #project = :project, #model = :model, #staging = :staging',
        ExpressionAttributeValues: {
            ':zero': {
                'N': '0',
            },
            ':cost': {
                'N': String(cost),
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
    try {
        const body = JSON.parse(event.body);
        let model = body.model ? body.model : event.rawPath.match(/\/engines\/([^\/]+)/)[1];
        if (!prices[model]) {
            model = model.substring(0, model.lastIndexOf('-'));
        }
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
            'OpenAI-Organization': process.env.OPENAI_ORG_ID,
        };
        const caching = event.headers['openai-proxy-caching'] || '1';
        const user = event.headers['openai-proxy-user'];
        const project = event.headers['openai-proxy-project'] || 'N/A';
        const staging = context.functionName.split('-').pop();
        console.log(user, project, model, staging);
        let url = 'https://api.openai.com/v1' + event.rawPath;
        if (event.rawQueryString && event.rawQueryString != '') {
            url = url + '?' + event.rawQueryString;
        }

        let key;
        if (memcachedClient && caching != '0') {
            key = crypto.createHash('sha256').update(event.body).digest('hex');
            console.log('Cache key: ' + key)
            const cachedResponse = await new Promise(resolve => memcachedClient.get(key, (err, data) => {
                if (err) throw err;
                resolve(data)
            }));
            if (cachedResponse) {
                console.log('Cache hit');
                const httpResponse = JSON.parse(cachedResponse);
                responseStream = awslambda.HttpResponseStream.from(responseStream, {
                    statusCode: httpResponse.status,
                    headers: httpResponse.headers,
                });
                responseStream.write(httpResponse.data);
                responseStream.end();
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

        let httpResponse;
        try {
            httpResponse = await axios({
                method: 'POST',
                url: url,
                data: event.body,
                headers: headers,
                responseType: 'stream',
                timeout: 600 * 1000, // 10 minutes
            });
            responseStream = awslambda.HttpResponseStream.from(responseStream, {
                statusCode: httpResponse.status,
                headers: httpResponse.headers,
            });
        } catch (error) {
            await pipeline(
                error.response.data,
                awslambda.HttpResponseStream.from(responseStream, {
                    statusCode: error.response.status,
                    headers: error.response.headers,
                }),
            );
            return;
        }

        bufferStream = new BufferStream();
        await pipeline(
            httpResponse.data,
            bufferStream,
            responseStream,
        );

        const buffer = bufferStream.getBuffer().toString();
        let prompt_tokens, completion_tokens;
        if (!body.stream) {
            const response = JSON.parse(buffer);
            if (!response.error) {
                prompt_tokens = response.usage.prompt_tokens;
                completion_tokens = response.usage.completion_tokens;
            }
        } else {
            const CHARS_PER_TOKEN = 4; // estimate tokens
            prompt_tokens = parseInt(body.messages.reduce((acc, message) =>
                acc + message.content.length, 0
            ) / CHARS_PER_TOKEN);
            let chunks = buffer.split('\n\n');
            completion_tokens = parseInt(chunks.slice(0, chunks.length - 3).reduce((acc, chunk) =>
                acc + JSON.parse(chunk.slice('data: '.length)).choices[0].delta.content.length, 0
            ) / CHARS_PER_TOKEN);
        }

        if (prompt_tokens && completion_tokens) {
            console.log('Usage: ' + prompt_tokens + ' input tokens + ' + completion_tokens + ' output tokens');
            const cost = calculateCost(
                model,
                prompt_tokens,
                completion_tokens
            );
            await updateUsage(user, project, model, staging, cost);
            await updateUsage('*', project, model, staging, cost);
            await updateUsage('*', project, '*', staging, cost);
        }

        if (memcachedClient && caching != '0') {
            const cachedResponse = JSON.stringify({
                data: buffer,
                status: httpResponse.status,
                headers: httpResponse.headers,
            });
            await new Promise((resolve, reject) => memcachedClient.set(key, cachedResponse, TTL, (err) => {
                if (err) {
                    reject(err);
                } else {
                    console.log('Cached');
                    resolve();
                }
            }));
        }

    } catch (error) {
        console.error(error);
        try {
            responseStream = awslambda.HttpResponseStream.from(responseStream, {
                statusCode: 500,
                headers: {
                    'Content-Type': 'application/json',
                }
            });
        } catch (error) {
        }
        responseStream.write(JSON.stringify({ message: error.message, stack: error.stack }));
        responseStream.end();
        return;
    }
});

if (require.main === module) { // For testing
    const event = {
        rawPath: '/chat/completions',
        body: JSON.stringify({
            messages: [
                { role: 'user', content: 'Tell me a story in 10 words' }
            ],
            model: 'gpt-3.5-turbo',
            stream: true,
        }),
        headers: {
            'openai-proxy-user': 'fulano',
            'openai-proxy-project': 'hello',
        },
    };
    const context = {
        functionName: 'openai-proxy-dev',
    };

    exports.lambdaHandler(event, context)
        .then()
        .catch(error => console.error(error));
}
