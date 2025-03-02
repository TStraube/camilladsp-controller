#!/bin/sh -e

PYCDSP_VERSION="v3.0.0"  # https://github.com/HEnquist/pycamilladsp/releases
PYCDSP_PLOT_VERSION="v3.0.0"  # https://github.com/HEnquist/pycamilladsp-plot/releases
PYALSA_VERSION="1.2.12"  # http://www.alsa-project.org/files/pub/pyalsa/pyalsa-1.2.12.tar.bz2

BUILD_DIR="/tmp/piCoreCDSPController"

### Exit, if not enough free space
requiredSpaceInMB=100
availableSpaceInMB=$(/bin/df -m /dev/mmcblk0p2 | awk 'NR==2 { print $4 }')
if [[ $availableSpaceInMB -le $requiredSpaceInMB ]]; then
    >&2 echo "Not enough free space"
    >&2 echo "Increase SD-Card size: Main Page > Additional functions > Resize FS"
    exit 1
fi

# Installs a module from the piCorePlayer repository - if not already installed.
# Call like this: install_if_missing module_name
install_if_missing(){
  if ! tce-status -i | grep -q "$1" ; then
    pcp-load -wil "$1"
  fi
}

# Installs a module from the piCorePlayer repository, at least until the next reboot - if not already installed.
# Call like this: install_temporarily_if_missing module_name
install_temporarily_if_missing(){
  if ! tce-status -i | grep -q "$1" ; then
    pcp-load -wil -t /tmp "$1" # Downloads to /tmp/optional and loads extensions temporarily
  fi
}

set -v



### Building camilladsp-controller and set up venv environment
install_temporarily_if_missing git
install_temporarily_if_missing compiletc
install_temporarily_if_missing libasound-dev
install_if_missing python3.11
install_temporarily_if_missing python3.11-pip
sudo mkdir -m 775 /usr/local/camilladsp-controller
sudo chmod ug+x /usr/local/camilladsp-controller
cd /usr/local
sudo git clone https://github.com/HEnquist/camilladsp-controller.git
sudo chown root:staff /usr/local/camilladsp-controller
cd /usr/local/camilladsp-controller
python3 -m venv --system-site-packages environment
(tr -d '\r' < environment/bin/activate) > environment/bin/activate_new # Create fixed version of the activate script. See https://stackoverflow.com/a/44446239
mv -f environment/bin/activate_new environment/bin/activate
source environment/bin/activate # activate custom python environment
python3 -m pip install --upgrade pip
pip install websocket_client aiohttp jsonschema setuptools
PYALSA_URL=http://www.alsa-project.org/files/pub/pyalsa/pyalsa-${PYALSA_VERSION}.tar.bz2
wget -O pyalsa.tar.bz2 $PYALSA_URL
pip install pyalsa.tar.bz2
pip install git+https://github.com/HEnquist/pycamilladsp.git@${PYCDSP_VERSION}
pip install git+https://github.com/HEnquist/pycamilladsp-plot.git@${PYCDSP_PLOT_VERSION}
deactivate # deactivate custom python environment
rm -f pyalsa.tar.bz2

### Saving changes and rebooting

#pcp backup
#pcp reboot