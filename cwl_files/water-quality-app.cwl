cwlVersion: v1.0
$namespaces:
  s: https://schema.org/
s:softwareVersion: 0.1.2
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf
$graph:
  # Workflow entrypoint
  - class: Workflow
    id: water-quality
    label: Water quality
    doc: Water quality index calculation
    requirements:
      ResourceRequirement:
        coresMax: 2
        ramMax: 4096
    inputs:
      stac_collection:
        label: STAC collection
        doc: The STAC collection to use
        type: string
      aoi:
        label: Area
        doc: The area of interest as GeoJSON
        type: string
      date_start:
        label: Date start
        doc: The start date for the STAC item search
        type: string
      date_end:
        label: Date end
        doc: The start date for the STAC item search
        type: string
      clip:
        label: Clip
        doc: A flag indicating whether to crop the data to the AOI footprint
        type: string
      limit:
        label: Limit
        doc: Max number of STAC items to process
        type: string
    outputs:
      - id: results
        type: Directory
        outputSource:
          - water_quality/results
    steps:
      water_quality:
        run: "#water_quality"
        in:
          stac_collection: stac_collection
          aoi: aoi
          date_start: date_start
          date_end: date_end
          limit: limit
          clip: clip
        out:
          - results

  # calculator
  - class: CommandLineTool
    id: water_quality
    requirements:
      ResourceRequirement:
        coresMax: 2
        ramMax: 4096
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: [ "eodh", "water", "quality" ]
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
      clip:
        type: string
        inputBinding:
          position: 5
          prefix: --clip
      limit:
        type: string
        inputBinding:
          position: 6
          prefix: --limit
    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./data/stac-catalog/
