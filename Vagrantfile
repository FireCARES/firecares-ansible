# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.box = "ubuntu/trusty"
  config.vm.box_url = "https://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box"

  config.vm.define "default", primary: true do |default|
    default.vm.network :private_network, ip: "192.168.33.15"
    default.vm.synced_folder "../firecares", "/firecares", mount_options: ["dmode=777,fmode=777"]
    default.vm.network "forwarded_port", guest: 8888, host: 8888
    default.vm.network "forwarded_port", guest: 8089, host: 8089

    default.vm.provider :virtualbox do |vb|
        vb.customize ["modifyvm", :id, "--name", "FireCARES", "--memory", ENV['VM_MEMORY'] || "8000"]
    end

    default.vm.provision "ansible" do |ansible|
        ansible.playbook = "vagrant.yml"
        ansible.host_key_checking = false
        ansible.verbose = "v"
    end
  end
end
