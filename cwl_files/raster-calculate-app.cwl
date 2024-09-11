cwlVersion: v1.0
$namespaces:
  s: https://schema.org/
s:softwareVersion: 0.1.2
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf
$graph:
  # Workflow entrypoint
  - class: Workflow
    id: raster-calculate
    label: Test raster calculator for Spyrosoft workflows
    doc: Test raster calculator for Spyrosoft workflows
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 1024
    inputs:
      stac_collection:
        label: stac collection to use
        doc: stac collection to use
        type: string
      aoi:
        label: lorem ipsum dolor sit amet
        doc: lorem ipsum dolor sit amet
        type: string
      date_start:
        label: lorem ipsum dolor sit amet
        doc: lorem ipsum dolor sit amet
        type: string
      date_end:
        label: lorem ipsum dolor sit amet
        doc: lorem ipsum dolor sit amet
        type: string
      index:
        label: lorem ipsum dolor sit amet
        doc: lorem ipsum dolor sit amet
        type: string

    outputs:
      - id: results
        type: Directory
        outputSource:
          - calculator/results
    steps:
      calculator:
        run: "#calculator"
        in:
          stac_collection: stac_collection
          aoi: aoi
          date_start: date_start
          date_end: date_end
          index: index
        out:
          - results
  # calculator
  - class: CommandLineTool
    id: calculator
    requirements:
      ResourceRequirement:
        coresMax: 1
        ramMax: 512
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: ["eodh", "raster", "calculate"]
    inputs:
      stac_collection:
        type: string
        inputBinding:
          position: 1
          prefix: --stac_collection
      aoi:
        type: string
        inputBinding:
          position: 2
          prefix: --aoi
      date_start:
        type: string
        inputBinding:
          position: 3
          prefix: --date_start
      date_end:
        type: string
        inputBinding:
          position: 4
          prefix: --date_end
      index:
        type: string
        inputBinding:
          position: 5
          prefix: --index

    outputs:
      results:
        type: Directory
        outputBinding:
          glob: .
