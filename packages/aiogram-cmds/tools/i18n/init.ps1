param(
    [Parameter(Mandatory=$true)][string]$Locale,
    [string]$Domain = "messages",
    [string]$Locales = "examples/locales"
)

poetry run pybabel init -i "$Locales/$Domain.pot" -d "$Locales" -D "$Domain" -l "$Locale"

