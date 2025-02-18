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
      index:
        label: Index
        doc: The spectral index to calculate
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
          limit: limit
          clip: clip
        out:
          - results

  # calculator
  - class: CommandLineTool
    id: calculator
    requirements:
      ResourceRequirement:
        coresMax: 2
        ramMax: 4096
      EnvVarRequirement:
        envDef:
          ENVIRONMENT: <<ENVIRONMENT>>
          SENTINEL_HUB__CLIENT_ID: <<SENTINEL_HUB__CLIENT_ID>>
          SENTINEL_HUB__CLIENT_SECRET: <<SENTINEL_HUB__CLIENT_SECRET>>
          SENTINEL_HUB__STAC_API_ENDPOINT: <<SENTINEL_HUB__STAC_API_ENDPOINT>>
          EODH__STAC_API_ENDPOINT: <<EODH__STAC_API_ENDPOINT>>
    hints:
      DockerRequirement:
        dockerPull: ghcr.io/eo-datahub/eodh-workflows:latest
    baseCommand: [ "eodh", "raster", "calculate" ]
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
      clip:
        type: string
        inputBinding:
          position: 6
          prefix: --clip
      limit:
        type: string
        inputBinding:
          position: 7
          prefix: --limit
    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./data/stac-catalog/
