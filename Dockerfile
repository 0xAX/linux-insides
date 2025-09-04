FROM lrx0014/gitbook:3.2.3
COPY ./ /srv/gitbook/
EXPOSE 4000

# Update sources.list for Debian Jessie.
RUN rm /etc/apt/sources.list
RUN echo "deb http://archive.debian.org/debian-security jessie/updates main" >> /etc/apt/sources.list.d/jessie.list
RUN echo "deb http://archive.debian.org/debian jessie main" >> /etc/apt/sources.list.d/jessie.list
RUN apt update
RUN apt install -y --force-yes bzip2 calibre inkscape

# Run CommandBox shell with gitbook command available. (https://www.forgebox.io/view/gitbook-exporter)
# Examples:
#RUN gitbook pdf
#RUN gitbook epub

