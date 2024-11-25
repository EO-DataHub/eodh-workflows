cwlVersion: v1.0
$namespaces:
  s: https://schema.org/
s:softwareVersion: 0.1.2
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf
$graph:
  # Workflow entrypoint
  - class: Workflow
    id: lulc-change-wf
    label: LULC change
    doc: LULC change
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 1024
    inputs:
      source:
        label: source
        doc: data source to be processed
        type: string
      aoi:
        label: aoi
        doc: area of interest as GeoJSON
        type: string
      date_start:
        label: start date
        doc: start date for data queries in ISO 8601
        type: string
      date_end:
        label: end date
        doc: end date for data queries in ISO 8601
        type: string

    outputs:
      - id: results
        type: Directory
        outputSource:
          - generate-thumbnails/results
    steps:
      download:
        run: "#download"
        in:
          source: source
          aoi: aoi
          date_start: date_start
          date_end: date_end
        out:
          - results
      clip:
        run: "#clip"
        in:
          input_stac: download/results
          aoi: aoi
        out:
          - results
      lulc-change:
        run: "#lulc-change"
        in:
          input_stac: clip/results
        out:
          - results
      generate-thumbnails:
        run: "#generate-thumbnails"
        in:
          input_stac: lulc-change/results
        out:
          - results

  # download
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

    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./data/downloaded/

  # clip
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

  # lulc-change
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

  # generate-thumbnails
  - class: CommandLineTool
    id: generate-thumbnails
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "raster", "thumbnails"]
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
          glob: ./data/thumbnails/
