# Fluxul Demo Kit SRL

  ```mermaid
  flowchart LR
    subgraph P2P["Procure-to-Pay (P1, P2)"]
      MR[Material Request] --> PO[Purchase Order] --> PR["Purchase Receipt<br/>+50 / componentă în Materii Prime"] --> PI[Purchase Invoice] --> PE1["Payment Entry (furnizor)"]
    end

    subgraph MFG["Producție (M1)"]
      BOM["BOM KIT-TEMP<br/>4 componente / kit"] --> WO["Work Order<br/>20 kituri"] --> SE1["Stock Entry: Transfer<br/>Materii Prime → Lucru in Curs"] --> SE2["Stock Entry: Manufacture<br/>-componente din Lucru in
  Curs<br/>+20 KIT în Produse Finite"]
    end

    subgraph O2C["Order-to-Cash (S1 Alfa Tech, S2 Beta)"]
      QTN["Quotation<br/>(doar S1)"] --> SO[Sales Order] --> DN["Delivery Note<br/>-KIT din Produse Finite<br/>(S1: -10, S2: -5)"] --> SI[Sales Invoice]
      SO -->|"S1: plată în avans"| PE2["Payment Entry (client)"]
      PE2 -.->|"Get Advances Received"| SI
    end

    PR -.->|componente| SE1
    SE2 -.->|KIT-TEMP| DN

    classDef stoc fill:#d9f2d9,stroke:#2e7d32
    classDef cont fill:#dbe9fb,stroke:#1565c0
    class PR,SE1,SE2,DN stoc
    class PI,PE1,SI,PE2 cont
  ```

  Verde = mișcă stocul (Stock Ledger). Albastru = doar contabilitate (General Ledger).
  Săgețile punctate dintre blocuri arată unde ajunge marfa.

  | Document | Stoc (Stock Ledger) | Contabilitate (General Ledger) |
  |---|---|---|
  | Purchase Receipt | +componente în Materii Prime - DK | Dr Stock In Hand / Cr Stock Received But Not Billed |
  | Purchase Invoice | — | Dr Stock Received But Not Billed / Cr Creditors |
  | Payment Entry (furnizor) | — | Dr Creditors / Cr Cash |
  | Stock Entry: Transfer | Materii Prime → Lucru in Curs | — (ambele depozite au contul Stock In Hand) |
  | Stock Entry: Manufacture | -componente din Lucru in Curs, +KIT în Produse Finite | — (același cont) |
  | Delivery Note | -KIT din Produse Finite | Dr Cost of Goods Sold / Cr Stock In Hand (S1: 1.500) |
  | Sales Invoice | — | Dr Debtors / Cr Sales (S1: 4.800, S2: 2.250) |
  | Payment Entry (client, S1) | — | Dr Cash / Cr Debtors 4.800, plătit înainte de factură, apoi alocat pe ea |