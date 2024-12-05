  - class: CommandLineTool
    id: download
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
      EnvVarRequirement:
        envDef:
          SH_CLIENT_ID: <<SENTINEL_HUB__CLIENT_ID>>
          SH_SECRET: <<SENTINEL_HUB__CLIENT_SECRET>>
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "raster", "download"]
    inputs:
      source:
        type: string
        inputBinding:
          position: 2
          prefix: --source
      aoi:
        type: string
        inputBinding:
          position: 3
          prefix: --aoi
      date_start:
        type: string
        inputBinding:
          position: 4
          prefix: --date_start
      date_end:
        type: string
        inputBinding:
          position: 5
          prefix: --date_end
