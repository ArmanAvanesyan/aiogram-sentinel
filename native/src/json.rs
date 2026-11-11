//! Single-pass strict JSON parser, preserving order and arbitrary integer lexemes.
use serde_json::{Map, Value};

pub fn parse(raw: &str, max_bytes: usize, max_depth: usize) -> Result<Value, String> {
    if max_depth > 512 {
        return Err("JSON nesting policy exceeds supported bound".into());
    }
    if raw.len() > max_bytes {
        return Err("JSON exceeds byte limit".into());
    }
    let mut scan = Scan {
        bytes: raw.as_bytes(),
        at: 0,
        max_depth,
    };
    let value = scan.value(0)?;
    scan.ws();
    if scan.at != scan.bytes.len() {
        return Err("Trailing JSON data".into());
    }
    Ok(value)
}
struct Scan<'a> {
    bytes: &'a [u8],
    at: usize,
    max_depth: usize,
}
impl Scan<'_> {
    fn ws(&mut self) {
        while self.at < self.bytes.len()
            && matches!(self.bytes[self.at], b' ' | b'\t' | b'\r' | b'\n')
        {
            self.at += 1;
        }
    }
    fn take(&mut self, byte: u8) -> Result<(), String> {
        self.ws();
        if self.bytes.get(self.at) != Some(&byte) {
            return Err("Malformed JSON delimiter".into());
        }
        self.at += 1;
        Ok(())
    }
    fn string(&mut self) -> Result<String, String> {
        self.ws();
        let start = self.at;
        self.take(b'"')?;
        let mut escaped = false;
        while let Some(&byte) = self.bytes.get(self.at) {
            self.at += 1;
            if !escaped && byte == b'"' {
                return serde_json::from_slice(&self.bytes[start..self.at])
                    .map_err(|_| "Invalid JSON string or Unicode".into());
            }
            if !escaped && byte < 32 {
                return Err("Unescaped JSON control character".into());
            }
            escaped = !escaped && byte == b'\\';
        }
        Err("Unterminated JSON string".into())
    }
    fn value(&mut self, depth: usize) -> Result<Value, String> {
        if depth > self.max_depth {
            return Err("JSON nesting limit exceeded".into());
        }
        self.ws();
        match self.bytes.get(self.at).copied() {
            Some(b'{') => {
                self.at += 1;
                self.ws();
                let mut values = Map::new();
                if self.bytes.get(self.at) == Some(&b'}') {
                    self.at += 1;
                    return Ok(Value::Object(values));
                }
                loop {
                    let key = self.string()?;
                    if values.contains_key(&key) {
                        return Err("Duplicate JSON object key".into());
                    }
                    self.take(b':')?;
                    let value = self.value(depth + 1)?;
                    values.insert(key, value);
                    self.ws();
                    if self.bytes.get(self.at) == Some(&b'}') {
                        self.at += 1;
                        break;
                    }
                    self.take(b',')?;
                }
                Ok(Value::Object(values))
            }
            Some(b'[') => {
                self.at += 1;
                self.ws();
                let mut values = Vec::new();
                if self.bytes.get(self.at) == Some(&b']') {
                    self.at += 1;
                    return Ok(Value::Array(values));
                }
                loop {
                    values.push(self.value(depth + 1)?);
                    self.ws();
                    if self.bytes.get(self.at) == Some(&b']') {
                        self.at += 1;
                        break;
                    }
                    self.take(b',')?;
                }
                Ok(Value::Array(values))
            }
            Some(b'"') => self.string().map(Value::String),
            Some(_) => {
                let start = self.at;
                while let Some(byte) = self.bytes.get(self.at) {
                    if matches!(byte, b',' | b']' | b'}' | b' ' | b'\t' | b'\n' | b'\r') {
                        break;
                    }
                    self.at += 1;
                }
                if start == self.at {
                    return Err("Missing JSON value".into());
                }
                let token = std::str::from_utf8(&self.bytes[start..self.at])
                    .map_err(|_| "Invalid UTF-8")?;
                let value: Value =
                    serde_json::from_str(token).map_err(|_| "Malformed JSON scalar")?;
                if let Value::Number(number) = &value {
                    if token.contains(['.', 'e', 'E'])
                        && !number.as_f64().is_some_and(f64::is_finite)
                    {
                        return Err("Non-finite JSON number".into());
                    }
                }
                Ok(value)
            }
            None => Err("Missing JSON value".into()),
        }
    }
}
