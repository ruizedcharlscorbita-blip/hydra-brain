name: Bug report
description: Create a report to help us improve Hydra
labels: [bug]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting this issue! Please provide as much detail as possible to help us diagnose and resolve the problem.
  - type: textarea
    id: description
    attributes:
      label: Description
      description: Describe what the bug is.
      placeholder: E.g., The health monitor fails to ping certain models because of a specific response code.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: What steps did you take to encounter the bug?
      placeholder: |
        1. Run python -m inventory.sync_openrouter
        2. ...
    validations:
      required: true
  - type: textarea
    id: output
    attributes:
      label: Command Output / Logs
      description: Copy and paste command line output or logs from `logs/hydra.log` if applicable.
      render: shell
  - type: textarea
    id: environment
    attributes:
      label: Environment Info
      description: OS version, Python version, configuration mode.
      placeholder: E.g., Windows 11, Python 3.12.3, HYDRA_MOCK=false
