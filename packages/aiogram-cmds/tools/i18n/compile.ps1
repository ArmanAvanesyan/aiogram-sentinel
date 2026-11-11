param(
    [string]$Locales = "examples/locales"
)

poetry run pybabel compile -d "$Locales"

