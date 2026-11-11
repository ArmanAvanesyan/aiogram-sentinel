use serde::Deserialize;
use std::collections::{HashMap, HashSet};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub parent: Option<String>,
    pub renderer: Option<String>,
    pub back_to: Option<String>,
    pub cancel_to: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Spec {
    roots: Vec<String>,
    nodes: Vec<Node>,
    #[serde(default)]
    migrations: HashMap<String, String>,
    safe_root: Option<String>,
}

/// Linear-size compiled graph. Ancestor paths are materialized only on request.
pub struct Graph {
    pub nodes: HashMap<String, Node>,
    root_targets: HashMap<String, String>,
    roots: HashSet<String>,
    migrations: HashMap<String, String>,
    safe_root: Option<String>,
    pub cancel: HashMap<String, String>,
}
fn identifier(value: &str) -> bool {
    !value.is_empty() && value.chars().count() <= 256
}
impl Graph {
    pub fn compile(raw: &str) -> Result<Self, String> {
        super::json::parse(raw, 8_388_608, 64)?;
        let spec: Spec = serde_json::from_str(raw).map_err(|_| "Malformed registry")?;
        let mut nodes = HashMap::new();
        for node in spec.nodes {
            if !identifier(&node.id)
                || [&node.parent, &node.renderer, &node.back_to, &node.cancel_to]
                    .iter()
                    .any(|x| x.as_ref().is_some_and(|x| !identifier(x)))
            {
                return Err("Invalid registry identifier".into());
            }
            if nodes.insert(node.id.clone(), node).is_some() {
                return Err("Duplicate node ID".into());
            }
        }
        let roots: HashSet<_> = spec.roots.into_iter().collect();
        if roots.is_empty()
            || roots.iter().any(|id| {
                !nodes
                    .get(id)
                    .is_some_and(|n| n.parent.is_none() && n.renderer.is_some())
            })
        {
            return Err("Invalid registry roots".into());
        }
        for node in nodes.values() {
            for target in [&node.back_to, &node.cancel_to].into_iter().flatten() {
                if !nodes.get(target).is_some_and(|n| n.renderer.is_some()) {
                    return Err("Invalid navigation target".into());
                }
            }
        }
        let mut root_targets: HashMap<String, String> = roots
            .iter()
            .map(|root| (root.clone(), root.clone()))
            .collect();
        let mut cancel: HashMap<String, String> = roots
            .iter()
            .map(|root| {
                (
                    root.clone(),
                    nodes[root]
                        .cancel_to
                        .clone()
                        .unwrap_or_else(|| root.clone()),
                )
            })
            .collect();
        for node in nodes.values() {
            if root_targets.contains_key(&node.id) {
                continue;
            }
            let mut seen = HashSet::new();
            let mut path = Vec::new();
            let mut current = node;
            while !root_targets.contains_key(&current.id) {
                if !seen.insert(current.id.clone()) {
                    return Err("Parent cycle".into());
                }
                path.push(current.id.clone());
                let parent = current.parent.as_ref().ok_or("Parentless non-root node")?;
                current = nodes.get(parent).ok_or("Missing parent")?;
            }
            let root = root_targets[&current.id].clone();
            let mut inherited_cancel = cancel[&current.id].clone();
            for id in path.into_iter().rev() {
                inherited_cancel = nodes[&id].cancel_to.clone().unwrap_or(inherited_cancel);
                root_targets.insert(id.clone(), root.clone());
                cancel.insert(id, inherited_cancel.clone());
            }
        }
        if spec
            .safe_root
            .as_ref()
            .is_some_and(|id| !roots.contains(id))
        {
            return Err("Invalid safe root".into());
        }
        for (source, target) in &spec.migrations {
            if source.is_empty()
                || nodes.contains_key(source)
                || !nodes.get(target).is_some_and(|n| n.renderer.is_some())
            {
                return Err("Invalid migration".into());
            }
        }
        Ok(Self {
            nodes,
            root_targets,
            roots,
            migrations: spec.migrations,
            safe_root: spec.safe_root,
            cancel,
        })
    }
    pub fn ancestors(&self, id: &str) -> Result<Vec<String>, String> {
        let mut node = self.nodes.get(id).ok_or("Unknown node")?;
        let mut path = Vec::new();
        loop {
            path.push(node.id.clone());
            if let Some(parent) = &node.parent {
                node = &self.nodes[parent];
            } else {
                return Ok(path);
            }
        }
    }
    pub fn resolve(&self, id: &str) -> Result<String, String> {
        if self.nodes.contains_key(id) {
            return Ok(id.to_owned());
        }
        self.migrations
            .get(id)
            .or(self.safe_root.as_ref())
            .cloned()
            .ok_or_else(|| "Unknown node requires migration".into())
    }
    pub fn root(&self, id: &str) -> Result<String, String> {
        self.root_targets
            .get(id)
            .cloned()
            .ok_or_else(|| "Unknown node".into())
    }
    pub fn roots(&self) -> usize {
        self.roots.len()
    }
}
