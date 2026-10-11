Vagrant.configure("2") do |config|
  # Pont réseau automatique entre WSL et Windows
  config.vm.network "forwarded_port", guest: 22, host: 2222, host_ip: "0.0.0.0", id: "ssh", auto_correct: true
  config.ssh.host = `ip route show | grep -i default | awk '{ print $3}'`.strip
  
  # Utilisation d'une image Ubuntu 22.04 standard pour toutes les machines
  config.vm.box = "ubuntu/jammy64"
  
  # Configuration globale VirtualBox (Sans interface graphique)
  config.vm.provider "virtualbox" do |vb|
    vb.gui = false
    vb.customize ["modifyvm", :id, "--uart1", "off"]
    vb.customize ["modifyvm", :id, "--uartmode1", "disconnected"]
  end

  # ==========================================
  # 1. Configuration de la VM Controller
  # ==========================================
  config.vm.define "controller" do |controller|
    controller.vm.hostname = "controller"
    # Adresse IP fixe sur le réseau privé virtuel
    controller.vm.network "private_network", ip: "192.168.56.10"
    
    controller.vm.provider "virtualbox" do |vb|
      vb.name = "STI_Controller"
      vb.memory = "512" # RAM réduite à 512 Mo
      vb.cpus = 2
    end
  end

  # ==========================================
  # 2. Configuration des VMs Workers
  # ==========================================
  
  # WORKER 1
  config.vm.define "worker1" do |worker1|
    worker1.vm.hostname = "worker1"
    worker1.vm.network "private_network", ip: "192.168.56.11"
    
    worker1.vm.provider "virtualbox" do |vb|
      vb.name = "STI_Worker1"
      vb.memory = "512" # RAM réduite à 512 Mo
      vb.cpus = 1
    end
  end

  # WORKER 2
  config.vm.define "worker2" do |worker2|
    worker2.vm.hostname = "worker2"
    worker2.vm.network "private_network", ip: "192.168.56.12"
    
    worker2.vm.provider "virtualbox" do |vb|
      vb.name = "STI_Worker2"
      vb.memory = "512" # RAM réduite à 512 Mo
      vb.cpus = 1
    end
  end

  # WORKER 3
  config.vm.define "worker3" do |worker3|
    worker3.vm.hostname = "worker3"
    worker3.vm.network "private_network", ip: "192.168.56.13"
    
    worker3.vm.provider "virtualbox" do |vb|
      vb.name = "STI_Worker3"
      vb.memory = "512" # RAM réduite à 512 Mo
      vb.cpus = 1
    end
  end
end