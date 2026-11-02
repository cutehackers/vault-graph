# Vault Layers Are an Open Set

**Status:** Accepted, 2026-11-02

**Question:** Which Vault layers does vault-graph serve?

**Decision:** vault-graph does not hard-code the set of Vault layers. `personal` and `project` are the default layers. An owner can register more layers, such as `team`, without code changes.

**Reason:** The user corrected a design recommendation that presented "project + personal" as a fixed scope: "personal and project will. be the default vault layer. there could be possibly added team layer by its owner." (bake correction `2026-11-02-vault-layers-open`)

**Implications:**

- Design recommendations and option lists present the layer set as configurable, never as a fixed "project + personal" scope.
- Code or schema that lists layers reads them from configuration or registration, not from a closed list.
