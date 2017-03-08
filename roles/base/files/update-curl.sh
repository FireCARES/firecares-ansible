VER=`curl --version | head -c 11`

if [ "$VER" != "curl 7.47.0" ]
then

  sudo apt-get -y build-dep curl

  # Get latest (as of Feb 25, 2016) libcurl
  mkdir ~/curl
  cd ~/curl
  wget http://curl.haxx.se/download/curl-7.47.0.tar.bz2
  tar -xvjf curl-7.47.0.tar.bz2
  cd curl-7.47.0

  # The usual steps for building an app from source
  ./configure
  make
  sudo make install

  # Resolve any issues of C-level lib
  # location caches ("shared library cache")
  sudo ldconfig

fi
