param(
    [string]$Domain = "messages",
    [string]$Src = "src",
    [string]$Examples = "examples",
    [string]$Locales = "examples/locales"
)

poetry run pybabel extract -F babel.cfg -k _ -k ngettext -o "$Locales/$Domain.pot" $Src $Examples

