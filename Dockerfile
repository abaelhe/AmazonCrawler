
# here "./context_dir" denotes docker build's context directory;
#$ mkdir docker_workspace/ && cd docker_workspace/
#$ mkdir -p cache db log tmp data ./context_dir/src
#$ cd ./context_dir/src
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/s/sudo/sudo_1.8.27-1+deb10u2_amd64.deb'
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/o/openssl/libssl3_3.0.0~~alpha4-1_amd64.deb'
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/o/openssl/libssl-dev_3.0.0~~alpha4-1_amd64.deb'
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/o/openssl/openssl_3.0.0~~alpha4-1_amd64.deb'
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/c/ca-certificates/ca-certificates_20200601~deb10u1_all.deb'
#$ curl -O 'https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh'
#$ cd -
#$ docker plugin install --grant-all-permissions vieux/sshfs
#$ docker build --build-arg user=ops --tag 'abael.com/conda:python3.8.3' --force-rm --squash --compress --file ./Dockerfile  context_dir
#
FROM debian:buster-slim
ARG user
ENV username=${user:-ops}

# Debian/Ubuntu debconf noninteractive mode
ENV DEBIAN_FRONTEND=noninteractive

ENV PATH="/opt/conda/bin:${PATH}" LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=xterm
LABEL "miniconda"="2020-07-29-00:13"
LABEL "python"="3.8.3"
LABEL "origin"="debian:buster-slim"
LABEL "sha256"="879457af6a0bf5b34b48c12de31d4df0ee2f06a8e68768e5758c3293b2daf688"
LABEL "com.abael.vendor"="Abael.com"
LABEL "com.abael.license"="BSD."
WORKDIR /root

EXPOSE 80/tcp
EXPOSE 80/udp
EXPOSE 443/tcp
EXPOSE 443/udp
EXPOSE 8088/tcp
EXPOSE 6666/tcp
EXPOSE 7777/tcp
EXPOSE 8888/tcp
EXPOSE 9999/tcp
VOLUME ["/var/cache", "/var/log", "/var/db", "/tmp", "/data"]

RUN cd ~ && echo "InstallStart: $(date -R)\nusername:${username}" > ~/Install.log
ADD src/* /tmp/

#apt
RUN dpkg -i /tmp/*.deb && rm -f /tmp/*.deb
RUN mv /etc/apt/sources.list /etc/apt/sources.list.origin &&echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ buster main contrib non-free\ndeb https://mirrors.tuna.tsinghua.edu.cn/debian/ buster-updates main contrib non-free\ndeb https://mirrors.tuna.tsinghua.edu.cn/debian/ buster-backports main contrib non-free\ndeb https://mirrors.tuna.tsinghua.edu.cn/debian-security buster/updates main contrib non-free\n' > /etc/apt/sources.list

#conda
RUN echo 'auto_activate_base: true\nauto_update_conda: false\nremote_connect_timeout_secs: 5\nremote_read_timeout_secs: 10\nalways_yes: true\nssl_verify: true\nchannel_alias: https://mirrors.tuna.tsinghua.edu.cn/anaconda\nchannels:\n  - defaults\nshow_channel_urls: true\ndefault_channels:\n  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main\n  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free\n  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r\n  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/pro\n  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2\ncustom_channels:\n  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n  msys2: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n  bioconda: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n  menpo: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n  simpleitk: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud' > /etc/condarc && chmod a+r /etc/condarc && ln -svf /etc/condarc ~/.condarc

#pip
RUN echo '[global]\nindex-url=https://pypi.tuna.tsinghua.edu.cn/simple\nextra-index-url=https://mirror.baidu.com/pypi/simple\n' > /etc/pip.conf && chmod a+r /etc/pip.conf && mkdir -p ~/.pip && ln -svf /etc/pip.conf ~/.pip/pip.conf

#apt packages
RUN apt-get update --fix-missing && \
    apt-get install -y ca-certificates apt-utils  sudo vim grep sed git xvfb vnc4server

RUN /bin/bash /tmp/Miniconda3-latest-Linux-x86_64.sh -b -p /opt/conda && rm -f /tmp/Miniconda3-latest-Linux-x86_64.sh && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

#python/conda packages
RUN /opt/conda/bin/conda install -y jupyter ipython notebook psutil pillow 
RUN /opt/conda/bin/pip install pytest-xvfb pyvirtualdisplay pyscreenshot

#keep docker image clean
RUN find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -afy && \
    apt-get clean

RUN /usr/sbin/addgroup "${username}" && /usr/sbin/adduser --quiet --system --shell /bin/bash --ingroup "${username}" --disabled-password "${username}" && \
    echo "${username}  ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    su - "${username}" -c 'ln -svf /etc/condarc ~/.condarc && mkdir -p ~/.pip/ && ln -svf /etc/pip.conf ~/.pip/pip.conf'

CMD [ "/bin/bash" ]

#$ docker run --init -i -t --publish-all  --volume pkgs:/src  debian:buster-slim /bin/bash
#$ docker run --user ops --workdir /home/ops  --init -i -t --publish-all  -v $(pwd)/cache:/var/cache -v $(pwd)/db:/var/db -v $(pwd)/log:/var/log -v $(pwd)/tmp:/tmp  -v $(pwd)/data:/data 'abael.com/conda:python3.8.3' /bin/bash
#$ docker run --user ops --workdir /home/ops  --init -i -t --publish-all  -v $(pwd)/cache:/var/cache -v $(pwd)/db:/var/db -v $(pwd)/log:/var/log -v $(pwd)/tmp:/tmp  -v $(pwd)/data:/data 'abael.com/conda:python3.8.3' /opt/conda/bin/jupyter notebook --notebook-dir=/data --ip='0.0.0.0' --port=8888 --no-browser
