const { DynamoDBClient, GetItemCommand, UpdateItemCommand } = require("@aws-sdk/client-dynamodb");
const Memcached = require('memcached');
const axios = require('axios');
const crypto = require('crypto');

const cacheEndpoint = process.env.ELASTICACHE || "";
const cachePort = 11211;
const memcachedClient = cacheEndpoint != "" ? new Memcached(`${cacheEndpoint}:${cachePort}`) : null;
const TTL = 60 * 60 * 24; // 1 day
const ddbClient = new DynamoDBClient();

const prices = {
    "gpt-3.5-turbo": [0.0015, 0.002],
    "gpt-3.5-turbo-16k": [0.003, 0.004],
    "gpt-3.5-turbo-instruct": [0.0015, 0.002],
    "gpt-4": [0.03, 0.06],
    "gpt-4-32k": [0.06, 0.12],
};

function calculateCost(model, inputTokens, outputTokens) {
    let price = prices[model] || [0, 0];
    return price[0] * inputTokens / 1000 + price[1] * outputTokens / 1000;
}

async function getUsageAndLimit(compositeKey) {
    let today = new Date();
    let currentMonth = (today.getMonth() + 1).toString().padStart(2, '0') + today.getFullYear().toString().slice(2, 4);

    let params = {
        TableName: "openai-usage",
        Key: {
            "composite_key": {
                "S": compositeKey
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
        TableName: "openai-usage",
        Key: {
            "composite_key": {
                "S": compositeKey
            }
        },
        UpdateExpression: "SET #month = if_not_exists(#month, :zero) + :cost, " +
            "#user = :user, #project = :project, #model = :model, #staging = :staging",
        ExpressionAttributeValues: {
            ":zero": {
                "N": '0',
            },
            ":cost": {
                "N": String(cost)
            },
            ":user": {
                "S": user,
            },
            ":project": {
                "S": project,
            },
            ":model": {
                "S": model,
            },
            ":staging": {
                "S": staging,
            },
        },
        ExpressionAttributeNames: {
            "#month": currentMonth,
            "#user": "user",
            "#project": "project",
            "#model": "model",
            "#staging": "staging",
        }
    };

    const command = new UpdateItemCommand(params);
    await ddbClient.send(command);
}

exports.lambdaHandler = async (event, context) => {
    const user = event.user;
    const project = event.project || 'N/A';
    const staging = process.env.STAGING;
    const content = atob(event.content);
    const headers = event.headers;
    headers.authorization = `Bearer ${process.env.OPENAI_API_KEY}`;
    headers['openai-organization'] = process.env.OPENAI_ORGANIZATION;
    let model = headers['openai-model'] || JSON.parse(content).model;
    if (!prices[model]) {
        model = model.substring(0, model.lastIndexOf('-'));
    }

    let key, result;
    if (memcachedClient && !event.nocache) {
        key = crypto.createHash('sha256').update(event.content).digest('hex');
        result = await new Promise(resolve => memcachedClient.get(key, (err, data) => {
            if (err) throw err;
            resolve(data)
        }));
        if (result) {
            console.log("Cache hit");
            return JSON.parse(result);
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
        method: event.method,
        url: event.url,
        data: content,
        headers: headers
    });

    const resp = httpResult.data;
    if (!resp.error) {
        const cost = calculateCost(
            model,
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens
        );
        await updateUsage(user, project, model, staging, cost);
        await updateUsage("*", project, model, staging, cost);
        await updateUsage("*", project, "*", staging, cost);
    }

    const response = {
        content: btoa(JSON.stringify(httpResult.data)),
        headers: httpResult.headers,
        reason_phrase: httpResult.statusText,
        status_code: httpResult.status
    };

    if (memcachedClient && !event.nocache) {
        await new Promise((resolve, reject) => memcachedClient.set(key, JSON.stringify(response), TTL, (err) => {
            if (err) {
                reject(err);
            } else {
                resolve();
            }
        }));
    }

    return response;
};

if (require.main === module) {
    process.env.STAGING = "dev";

    const event = {
        method: "POST",
        url: "https://api.openai.com/v1/chat/completions",
        content: btoa(
            JSON.stringify({
                messages: [
                    { role: "user", content: "Hello world" }
                ]
            })
        ),
        headers: {
            "content-type": "application/json",
            "openai-model": "gpt-3.5-turbo-0613",
        },
        project: "hello",
        user: "fulano"
    };

    exports.lambdaHandler(event, null)
        .then(response => {
            console.log(atob(response.content.toString()));
        })
        .catch(error => console.error(error));
}
