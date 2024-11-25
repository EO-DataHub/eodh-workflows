  - class: CommandLineTool
    id: lulc-change
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "lulc", "change"]
    inputs:
      input_stac:
        type: Directory
        inputBinding:
          position: 2
          prefix: --input_stac

    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./data/lulc_change/
