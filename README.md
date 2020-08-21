# AmazonCrawler
Interactive Crawler; So we can pass almost all kind of Robot Prevention mechanism;
Since we use real people interaction when that is required, otherwise Full Automation;

Order Public Copyright Books at amazon.cn/amazon.com;

How To Use, Execute command:
$pytest --capture=no --username 'abaelhe@icloud.com' --password 'MYPASSWORD'  amazon.py


In Docker:
docker run --init --expose 9999 --publish 127.0.0.1:9999:9999/tcp --workdir /root --volume pkgs:/src -i -t debian:buster-slim /bin/bash
