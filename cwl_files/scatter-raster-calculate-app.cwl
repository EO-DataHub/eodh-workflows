cwlVersion: v1.0

$namespaces:
  s: https://schema.org/
s:softwareVersion: 1.1.8
schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf

$graph:
  - class: Workflow

    id: scatter-raster-calculate
    label: Test raster calculator for Spyrosoft workflows
    doc: Test raster calculator for Spyrosoft workflows

    requirements:
      - class: ResourceRequirement
        coresMax: 2
        ramMax: 8192
      - class: ScatterFeatureRequirement

    inputs:
      areas:
        label: areas of interest
        doc: areas of interest as a polygon
        type: string[]
      stac_collection:
        label: STAC collection
        doc: The STAC collection to use
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
          - stac_join/results

    steps:
      calculator:
        run: "#calculator"
        scatter: aoi
        in:
          stac_collection: stac_collection
          aoi: areas
          date_start: date_start
          date_end: date_end
          index: index
          limit: limit
          clip: clip
        out:
          - rc_results
      stac_join:
        run: "#stac_join"
        in:
          stac_catalog_dir:
            source: calculator/rc_results
        out:
          - results

  - class: CommandLineTool
    id: calculator
    requirements:
      ResourceRequirement:
        coresMax: 2
        ramMax: 8192
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
      rc_results:
        type: Directory
        outputBinding:
          glob: ./data/stac-catalog/

  - class: CommandLineTool
    id: stac_join
    requirements:
      ResourceRequirement:
        coresMax: 2
        ramMax: 8192
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
    baseCommand: [ "eopro", "stac", "join_v2" ]
    inputs:
      stac_catalog_dir:
        type:
          type: array
          items: Directory
          inputBinding:
            position: 1
            prefix: --stac_catalog_dir
    outputs:
      results:
        type: Directory
        outputBinding:
          glob: ./stac-join/
