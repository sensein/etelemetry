.PHONY: init plan apply destroy fmt validate

init:
	tofu init

plan:
	tofu plan

apply:
	tofu apply

destroy:
	@echo "WARNING: This will destroy all infrastructure!"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] && tofu destroy

fmt:
	tofu fmt -recursive

validate:
	tofu validate
