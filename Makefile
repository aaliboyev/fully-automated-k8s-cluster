.PHONY: help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Ansible
# =============================================================================
.PHONY: ansible-init ansible-join ansible-promote ansible-upgrade ansible-ping ansible-check

ANSIBLE_DIR := ansible
ANSIBLE_VARS := $(ANSIBLE_DIR)/group_vars/all.yml
ANSIBLE_PLAYBOOK := cd $(ANSIBLE_DIR) && ansible-playbook -e @group_vars/all.yml

ansible-init: ## [Ansible] Initialize fresh K8s cluster
	$(ANSIBLE_PLAYBOOK) playbooks/init-cluster.yml $(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")

ansible-join: ## [Ansible] Join worker nodes to the cluster
	$(ANSIBLE_PLAYBOOK) playbooks/join-workers.yml $(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")

ansible-promote: ## [Ansible] Add additional control plane nodes (HA)
	$(ANSIBLE_PLAYBOOK) playbooks/promote-controlplane.yml $(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")

ansible-upgrade: ## [Ansible] Upgrade K8s cluster to target version
	$(ANSIBLE_PLAYBOOK) playbooks/upgrade-cluster.yml $(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")

ansible-ping: ## [Ansible] Test connectivity to all nodes
	cd $(ANSIBLE_DIR) && ansible all -m ping

ansible-check: ## [Ansible] Dry-run init-cluster playbook
	$(ANSIBLE_PLAYBOOK) playbooks/init-cluster.yml --check $(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")
