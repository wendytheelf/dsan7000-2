如何標註：
1) 打開 review/manual_class_check.csv，針對每列填入 true_class（你認為的正解 canonical 類別）。
2) 存檔後執行第二段指令，會自動計算 top-1 accuracy。

備註：
- 若有 allowed_classes 名單，請以該名單為準。
- 若你希望人工用 Uniclass 或更細項，請先在 class_maps.yaml 定義口徑。
