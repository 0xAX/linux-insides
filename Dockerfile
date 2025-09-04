FROM lrx0014/gitbook:3.2.3
COPY ./ /srv/gitbook/
EXPOSE 4000

# Update sources.list for Debian Jessie.
RUN rm /etc/apt/sources.list
RUN echo "deb http://archive.debian.org/debian-security jessie/updates main" >> /etc/apt/sources.list.d/jessie.list
RUN echo "deb http://archive.debian.org/debian jessie main" >> /etc/apt/sources.list.d/jessie.list
RUN apt update
RUN apt install -y --force-yes calibre bzip2
RUN npm install svgexport@0.3.0 -g

# Install CommandBox (https://commandbox.ortusbooks.com/setup/installation).
# Requires OpenJDK 11 but only version 7 is available from Debian Jessie repositories.
# Run that on a more up-to-date system.
#RUN apt install -y libappindicator3-dev openjdk-11-jdk
#RUN curl -fsSl https://downloads.ortussolutions.com/debs/gpg | gpg --dearmor | tee /usr/share/keyrings/ortussolutions.gpg > /dev/null
#RUN echo "deb [signed-by=/usr/share/keyrings/ortussolutions.gpg] https://downloads.ortussolutions.com/debs/noarch /" | tee /etc/apt/sources.list.d/commandbox.list
#RUN apt-get update && apt-get install -y apt-transport-https commandbox

# Install gitbook-exporter into the CommandBox.
#RUN box install gitbook-exporter

# Run CommandBox shell with gitbook command available. (https://www.forgebox.io/view/gitbook-exporter)
# Examples:
#RUN gitbook pdf
#RUN gitbook epub

