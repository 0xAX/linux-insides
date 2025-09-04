FROM kyselejsyrecek/gitbook:3.2.3
COPY ./ /srv/gitbook/
EXPOSE 4000
WORKDIR /srv/gitbook
CMD ["sh", "-c", "/usr/local/bin/gitbook serve"]

# Examples:
#RUN gitbook pdf
#RUN gitbook epub

