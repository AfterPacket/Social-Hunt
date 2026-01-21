## Usage Examples with Smart State Parsing

# 1. Basic name search
python -m social_hunt.cli "john doe" --platforms peekyou

# 2. State abbreviation in query
python -m social_hunt.cli "pa/john_doe" --platforms peekyou
# Redirects to: https://www.peekyou.com/usa/pennsylvania/john_doe

also a inital at front

python -m social_hunt.cli "john doe",pa --platforms peekyou

full state name

python -m social_hunt.cli "california/jane_smith" --platforms peekyou

name with hyphen

python -m social_hunt.cli "mary_jane-doe",ny --platforms peekyou


## Supported State Formats

The smart state parser supports:
- **Two-letter abbreviations**: `pa`, `ca`, `ny`, `tx`
- **Full state names**: `pennsylvania`, `california`
- **With spaces or hyphens**: `new york`, `new-york`, `new_york`
- **US territories**: `dc`, `pr`, `gu`, `vi`, `mp`, `as`

## Name Formatting Rules

1. **Spaces** become **underscores**: `"John Doe"` → `"john_doe"`
2. **Hyphens** become **plus signs**: `"jane-doe"` → `"jane+doe"`

Has to be in this format:

"john doe" or with a hyphen "john smith-doe"
first last                   first last last

example

python -m social_hunt.cli "mary jane-doe",ny --platforms peekyou

mary jane-doe becomes mary_jane+doe

mixed will not work

john-doe-smith allen = john+doe+smith_allen
last last last first

# For ID crawl

John doe smith/pa

would be turned into

https://www.idcrawl.com/john-doe-smith/pennsylvania