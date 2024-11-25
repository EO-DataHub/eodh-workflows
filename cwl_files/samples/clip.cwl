  - class: CommandLineTool
    id: clip
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "raster", "clip"]
    inputs:
      input_stac:
        type: Directory
        inputBinding:
          position: 2
          prefix: --input_stac
      aoi:
        type: string
        inputBinding:
          position: 3
          prefix: --aoi

    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./data/clipped/
