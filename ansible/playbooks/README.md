# Ansible Playbooks

## init-cluster.yml

Initializes a fresh Kubernetes cluster from scratch.

**What it does:**
1. Prepares all nodes with Longhorn prerequisites (packages, kernel modules, services)
2. Runs Longhorn environment check on all nodes
3. Initializes the control plane with `kubeadm init`
4. Sets up kubectl for root user
5. Installs Calico CNI
6. Installs Longhorn storage

**Usage:**
```bash
ansible-playbook playbooks/init-cluster.yml
```

**Override versions:**
```bash
ansible-playbook playbooks/init-cluster.yml -e "longhorn_version=v1.8.1"
ansible-playbook playbooks/init-cluster.yml -e "calico_version=v3.29.2"
ansible-playbook playbooks/init-cluster.yml -e "longhorn_version=v1.8.1 calico_version=v3.29.2"
```

---

## join-workers.yml

Joins worker nodes to an existing cluster.

**Prerequisites:**
- Control plane must be initialized (run `init-cluster.yml` first)

**Usage:**
```bash
ansible-playbook playbooks/join-workers.yml
```

---

## promote-controlplane.yml

Adds additional control plane nodes for high availability (HA) setup.

**Prerequisites:**
- Primary control plane must be initialized
- Additional nodes must be in the `control_plane` group in inventory

**Usage:**
```bash
ansible-playbook playbooks/promote-controlplane.yml
```

---

## upgrade-cluster.yml

Upgrades Kubernetes cluster to a target version with proper rolling upgrade procedure.

**What it does:**
1. Upgrades control plane nodes one at a time (serial: 1)
   - Upgrades kubeadm
   - Runs `kubeadm upgrade apply` (first CP) or `kubeadm upgrade node` (additional CPs)
   - Drains the node
   - Upgrades kubelet and kubectl
   - Restarts kubelet
   - Uncordons the node
2. Upgrades worker nodes one at a time (serial: 1)
   - Drains the node
   - Upgrades kubeadm, kubelet, kubectl
   - Runs `kubeadm upgrade node`
   - Restarts kubelet
   - Uncordons the node
3. Verifies all nodes are Ready after upgrade

**Prerequisites:**
- Cluster must be running
- Target version must be set in `group_vars/all.yml` or passed as extra var

**Usage:**
```bash
# Upgrade to version in group_vars/all.yml
ansible-playbook playbooks/upgrade-cluster.yml

# Upgrade to specific version
ansible-playbook playbooks/upgrade-cluster.yml -e "kubernetes_version=v1.35.0"
```

**Notes:**
- Nodes already at target version are skipped
- Upgrades are done one node at a time to maintain cluster availability
- The playbook holds/unholds apt packages to prevent accidental upgrades
