# bash
ruff check src tests --output-format=json 2>/dev/null |
jq -r --arg root "$PWD/" '
  group_by(.filename)[] |
  .[0].filename as $file |
  (group_by(.code) |
    map({
      code: .[0].code,
      count: length
    })
  ) as $codes |
  "\([length] | add) \($file | sub("^" + $root; ""))  [" +
  ($codes |
    map(if .count > 1
        then "\(.code)×\(.count)"
        else .code
        end) |
    join(", ")
  ) + "]"
'