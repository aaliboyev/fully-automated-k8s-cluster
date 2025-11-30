#!/bin/bash
exec > >(tee -i /var/log/custom-script.log)
exec 2>&1
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# --- CONFIG -------------------------------------------------------------------

# Pause image used by containerd CRI
PAUSE_IMAGE="${PAUSE_IMAGE:-registry.k8s.io/pause:3.10}"

CONTAINERD_CONFIG="/etc/containerd/config.toml"

# ------------------------------------------------------------------------------

echo "[*] Starting Kubernetes base setup on $(hostname)"

echo "[*] Updating apt cache..."
apt-get update -y

echo "[*] Installing base + essential tools..."
apt-get install -y \
  ca-certificates \
  curl \
  wget \
  git \
  vim \
  nano \
  htop \
  apt-transport-https \
  gnupg \
  lsb-release \
  iptables ipset conntrack ebtables arptables ipset ipvsadm tcpdump bpftool iproute2 nftables

echo "[*] Ensuring NTP time sync is enabled..."
apt-get install -y systemd-timesyncd
systemctl enable --now systemd-timesyncd || true
timedatectl set-ntp true || true
timedatectl || true

echo "[*] Disabling swap..."
swapoff -a || true
# Comment out swap entries in fstab
if grep -q " swap " /etc/fstab; then
  sed -i.bak '/ swap / s/^\(.*\)$/#\1/' /etc/fstab
fi

echo "[*] Loading kernel modules..."
cat >/etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF

modprobe overlay || true
modprobe br_netfilter || true

echo "[*] Setting sysctl params for Kubernetes networking..."
cat >/etc/sysctl.d/99-kubernetes.conf <<EOF
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF
cat >/etc/sysctl.d/99-calico.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOF

sysctl --system

echo "[*] Installing containerd..."
apt-get install -y containerd

mkdir -p /etc/containerd

echo "[*] Generating default containerd config..."
containerd config default | tee "${CONTAINERD_CONFIG}" >/dev/null

echo "[*] Tuning containerd for Kubernetes (SystemdCgroup + pause image)..."
sed -i -E 's#^( *sandbox_image = ).*#\1"'"$PAUSE_IMAGE"'"#' "$CONTAINERD_CONFIG"
sed -i -E 's#SystemdCgroup *= *false#SystemdCgroup = true#' "$CONTAINERD_CONFIG"
sed -i -E 's#path = "/opt/containerd"#path = "/var/lib/containerd/opt"#' "$CONTAINERD_CONFIG"
sed -i -E 's#bin_dir = "/usr/lib/cni"#bin_dir = "/opt/cni/bin"#' "$CONTAINERD_CONFIG"

echo "[*] Restarting containerd with new config..."
systemctl daemon-reload
systemctl restart containerd

echo "[*] Server base setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run 'ansible-playbook -i inventory.ini playbooks/install-k8s.yml' to install Kubernetes components"
echo "  2. Run 'ansible-playbook -i inventory.ini playbooks/init-cluster.yml' to initialize control plane"
echo "  3. Run 'ansible-playbook -i inventory.ini playbooks/join-workers.yml' to join worker nodes"
