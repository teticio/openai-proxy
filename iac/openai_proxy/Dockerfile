FROM public.ecr.aws/lambda/nodejs:18
COPY package.json /var/task/
COPY app.js /var/task/
RUN npm install
CMD [ "app.lambdaHandler" ]
