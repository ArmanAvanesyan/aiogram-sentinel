param(
    [string]$Domain = "messages",
    [string]$Locales = "examples/locales"
)

poetry run pybabel update -i "$Locales/$Domain.pot" -d "$Locales" -D "$Domain"

