"""Vault memory writes (area M18, spec 2026-11-02 V1, 결정S1).

vault-graph never writes Vault files itself. This area checks the agent's fields, picks one Vault,
builds a Vault draft, and hands it to a writer port that composition supplies.
Import the owning module directly; this package exports nothing.
"""
