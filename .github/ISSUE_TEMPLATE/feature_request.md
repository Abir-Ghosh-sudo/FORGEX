name: Feature Request
description: Suggest a feature for FORGEX
title: "[Feature] "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: "# Feature Request"
  - type: textarea
    id: description
    attributes:
      label: Description
      description: What feature would you like to see?
    validations:
      required: true
  - type: textarea
    id: use-case
    attributes:
      label: Use Case
      description: What problem does this feature solve?
    validations:
      required: true
