# -*- mode: ruby -*-
WORKERS = {
  "worker1" => "192.168.56.11",
  "worker2" => "192.168.56.12",
  "worker3" => "192.168.56.13",
}

Vagrant.configure("2") do |config|
  config.vm.box = "generic/ubuntu2204"

  WORKERS.each do |name, ip|
    config.vm.define name do |node|
      node.vm.hostname = name
      node.vm.network "private_network",
        ip: ip,
        libvirt__network_name: "vagrant-workers",
        libvirt__netmask: "255.255.255.0",
        libvirt__dhcp_enabled: false

      node.vm.provider "virtualbox" do |vb|
        vb.name = name
        vb.memory = 1024
        vb.cpus = 1
      end

      node.vm.provider "libvirt" do |lv|
        lv.uri = "qemu:///system"
        lv.memory = 1024
        lv.cpus = 1
      end
    end
  end
end