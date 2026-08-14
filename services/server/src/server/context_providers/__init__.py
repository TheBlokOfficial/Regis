"""Dostawcy kontekstu — kategoria równoległa do pluginów (Warstwa 1-poziom).

Nie dostarczają narzędzi ani encji, tylko płaskie fakty o świecie i o
pochodzeniu requestu (wizja, sekcja 2, "Dostawca kontekstu"). Nic z tego
pakietu nie jest importowane przez `server.agent` (kernel) — dostawcy
rejestrują się w Gateway przez kontrakt
`server.agent.context_provider_contract.ContextProvider`.
"""
