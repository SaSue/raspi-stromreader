FROM alpine:latest

RUN apk update \ 
    && apk upgrade \
    && apk add --no-cache lighttpd
    
COPY lighttpd.conf /etc/lighttpd/lighttpd.conf

EXPOSE 80

CMD ["lighttpd", "-D", "-f", "/etc/lighttpd/lighttpd.conf"]