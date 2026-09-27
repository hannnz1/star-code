已修复 `openapi_types.py`，仅改了这一处文件，没有改测试，也没有加依赖。

修改内容：
- 为 `oneOf` 增加了 TypeScript 联合类型支持，输出与 `anyOf` 一致的联合类型表达式。
- 在 `allOf` 组合时，如果子表达式是联合类型，会自动加括号，避免优先级错误。
- 同时保留了原有的 `anyOf`、`allOf`、对象、数组等生成逻辑。

真实测试结果：
- 修复前先运行了 `python -m unittest -v`，结果失败，两个测试未通过：
  - `test_one_of_preserves_both_branches`
  - `test_union_is_grouped_inside_intersection`
- 修复后再次用完全相同的命令 `python -m unittest -v` 验证，结果通过：
  - `Ran 3 tests in 0.000s`
  - `OK`

如果你愿意，我也可以顺手帮你把这次改动总结成一段适合提交记录的中文 commit message。