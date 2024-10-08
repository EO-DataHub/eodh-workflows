cwlVersion: v1.0
$namespaces:
  s: https://schema.org/
s:softwareVersion: 0.1.2
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf
$graph:
  # Workflow entrypoint
  - class: Workflow
    id: lulc-change
    label: LULC change
    doc: LULC change
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 1024
    inputs:
      aoi:
        label: aoi
        doc: area of interest as GeoJSON
        type: string
      start_date:
        label: start date
        doc: start date for data queries in ISO 8601
        type: string
      end_date:
        label: end date
        doc: end date for data queries in ISO 8601
        type: string

    outputs:
      - id: results
        type: Directory
        outputSource:
          - change/results
    steps:
      change:
        run: "#change"
        in:
          aoi: aoi
          start_date: start_date
          end_date: end_date
        out:
          - results
  # change
  - class: CommandLineTool
    id: change
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "lulc", "change"]
    inputs:
      aoi:
        type: string
        inputBinding:
          position: 2
          prefix: --aoi
      start_date:
        type: string
        inputBinding:
          position: 3
          prefix: --start_date
      end_date:
        type: string
        inputBinding:
          position: 4
          prefix: --end_date

    outputs:
      results:
        type: Directory
        outputBinding:
          glob: .
