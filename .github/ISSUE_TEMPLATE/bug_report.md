name: Bug Report
description: File a bug report for FORGEX
title: "[Bug] "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: "# Bug Report"
  - type: textarea
    id: description
    attributes:
      label: Description
      description: What happened?
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What did you expect to happen?
    validations:
      required: true
  - type: dropdown
    id: os
    attributes:
      label: Operating System
      options: [Windows, Linux, macOS]
      default: 0
    validations:
      required: true
  - type: dropdown
    id: python
    attributes:
      label: Python Version
      options: ["3.11", "3.12", "3.13", "3.14"]
      default: 2
    validations:
      required: true
