The application settings.

::: eodh_workflows.core.settings

### Importing settings

To use current settings without the need to parse them each time you can use:

```python
import logging

from eodh_workflows.core.settings import current_settings


# log current environment
logging.info(current_settings.env)  # INFO:dev
```
