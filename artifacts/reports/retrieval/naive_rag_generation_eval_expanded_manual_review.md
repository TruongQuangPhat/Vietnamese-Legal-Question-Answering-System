# Naive RAG Manual Faithfulness Review

Status: `manual_review_partial`

This worksheet supports human claim-to-citation inspection. It does not prove semantic faithfulness or legal correctness and is not professional legal advice.

The Phase 9C.1 report contains answer previews and citation IDs, but not selected evidence text or citation summaries. Reviewers must inspect the underlying selected evidence before assigning a final verdict.

## Run Summary

- Source status: `expanded_generation_eval_passed`
- Cases: 5
- Generated answers: 4
- Fallback cases: 1
- Manual-review cases: 2
- All-caution cases: 2
- Priority review: `health_insurance_children_under_6_generation`, `marriage_conditions_generation`, `civil_rights_protection_generation`

## Reviewer Verdicts

Use one of: `pass`, `partial`, `fail`, `needs_more_evidence`, `not_applicable_for_fallback`.

## 1. `health_insurance_children_under_6_generation`

- Query: Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?
- Decision: `answer_allowed`
- LLM called: `true`
- Blocking: `true`
- Manual review required: `false`
- Selected evidence count: 5
- Caution selected count: 5
- All selected evidence caution: `true`
- Cited evidence IDs in preview: [E3], [E1], [E2]
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `all_selected_evidence_caution`

### Answer Preview

> Trẻ em dưới 6 tuổi là đối tượng tham gia bảo hiểm y tế [E3]. Thẻ bảo hiểm y tế của trẻ em dưới 6 tuổi có giá trị sử dụng đến ngày trẻ đủ 72 tháng tuổi. Nếu trẻ đủ 72 tháng tuổi mà chưa đến kỳ nhập học, thẻ bảo hiểm y tế sẽ có giá trị sử dụng đến ngày 30 tháng 9 của năm đó [E1]. Khi khám bệnh, chữa bệnh, trẻ em dưới 6 tuổi chưa được cấp thẻ bảo hiểm y tế phải xuất trình giấy tờ hợp pháp khác [E2].

### Citation Summaries

- Not available in the Phase 9C.1 report. Inspect the selected evidence and record the legal hierarchy, source, and supporting text here.

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Trẻ em dưới 6 tuổi là đối tượng tham gia bảo hiểm y tế [E3]. | [E3] | unchecked | |
| Thẻ bảo hiểm y tế của trẻ em dưới 6 tuổi có giá trị sử dụng đến ngày trẻ đủ 72 tháng tuổi. | none | unchecked | |
| Nếu trẻ đủ 72 tháng tuổi mà chưa đến kỳ nhập học, thẻ bảo hiểm y tế sẽ có giá trị sử dụng đến ngày 30 tháng 9 của năm đó [E1]. | [E1] | unchecked | |
| Khi khám bệnh, chữa bệnh, trẻ em dưới 6 tuổi chưa được cấp thẻ bảo hiểm y tế phải xuất trình giấy tờ hợp pháp khác [E2]. | [E2] | unchecked | |

### Manual Review Checklist

- [ ] Every material legal claim is supported by its cited evidence.
- [ ] Citation hierarchy and source metadata match the claim.
- [ ] The answer does not broaden conditions, exceptions, or scope.
- [ ] Caution evidence has been inspected and explained.
- [ ] Auxiliary context was not treated as directly citable evidence.
- [ ] Final verdict and reviewer notes are recorded.

Reviewer notes:

> Unchecked.

## 2. `annual_leave_days_generation`

- Query: Người lao động được nghỉ hằng năm bao nhiêu ngày?
- Decision: `fallback_required`
- LLM called: `false`
- Blocking: `true`
- Manual review required: `false`
- Selected evidence count: 5
- Caution selected count: 4
- All selected evidence caution: `false`
- Cited evidence IDs in preview: none
- Fallback reasons: exact_target_missing_in_eval_mode
- Preliminary reviewer verdict: `not_applicable_for_fallback`

### Selection Warnings

- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`

### Answer Preview

> Hiện tại hệ thống chưa tìm được căn cứ pháp lý đủ an toàn để trả lời chắc chắn. Các kết quả truy xuất có thể liên quan nhưng chưa đủ chính xác hoặc chưa đủ an toàn về điều/khoản/điểm để đưa ra câu trả lời có trích dẫn đáng tin cậy.

### Citation Summaries

- Not available in the Phase 9C.1 report. Inspect the selected evidence and record the legal hierarchy, source, and supporting text here.

### Fallback Review

| Check | Recorded state | Reviewer check | Notes |
| --- | --- | --- | --- |
| Fallback decision recorded | `fallback_required` | checked | |
| LLM was not called | `true` | checked | |
| Answer avoided unsupported legal claims | review answer preview | unchecked | |
| Fallback reason is acceptable | review fallback reasons | unchecked | |

### Manual Review Checklist

- [ ] Every material legal claim is supported by its cited evidence.
- [ ] Citation hierarchy and source metadata match the claim.
- [ ] The answer does not broaden conditions, exceptions, or scope.
- [ ] Caution evidence has been inspected and explained.
- [ ] Auxiliary context was not treated as directly citable evidence.
- [ ] Final verdict and reviewer notes are recorded.

Reviewer notes:

> Unchecked.

## 3. `civil_code_scope_generation`

- Query: Bộ luật Dân sự điều chỉnh những quan hệ nào?
- Decision: `answer_allowed`
- LLM called: `true`
- Blocking: `true`
- Manual review required: `false`
- Selected evidence count: 5
- Caution selected count: 0
- All selected evidence caution: `false`
- Cited evidence IDs in preview: [E1], [E5]
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- None recorded.

### Answer Preview

> Bộ luật Dân sự quy định về địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm [E1]. Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương khi tham gia quan hệ dân sự thì bình đẳng với các chủ thể khác và chịu trách nhiệm dân sự theo quy định [E5].

### Citation Summaries

- Not available in the Phase 9C.1 report. Inspect the selected evidence and record the legal hierarchy, source, and supporting text here.

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Bộ luật Dân sự quy định về địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm [E1]. | [E1] | unchecked | |
| Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương khi tham gia quan hệ dân sự thì bình đẳng với các chủ thể khác và chịu trách nhiệm dân sự theo quy định [E5]. | [E5] | unchecked | |

### Manual Review Checklist

- [ ] Every material legal claim is supported by its cited evidence.
- [ ] Citation hierarchy and source metadata match the claim.
- [ ] The answer does not broaden conditions, exceptions, or scope.
- [ ] Caution evidence has been inspected and explained.
- [ ] Auxiliary context was not treated as directly citable evidence.
- [ ] Final verdict and reviewer notes are recorded.

Reviewer notes:

> Unchecked.

## 4. `marriage_conditions_generation`

- Query: Điều kiện kết hôn theo pháp luật Việt Nam là gì?
- Decision: `answer_allowed`
- LLM called: `true`
- Blocking: `false`
- Manual review required: `true`
- Selected evidence count: 5
- Caution selected count: 5
- All selected evidence caution: `true`
- Cited evidence IDs in preview: [E2], [E1], [E3]
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`
- `all_selected_evidence_caution`

### Answer Preview

> Điều kiện kết hôn theo pháp luật Việt Nam bao gồm:
>
> *   Nam và nữ kết hôn với nhau phải do cả hai tự nguyện quyết định [E2].
> *   Việc kết hôn không thuộc các trường hợp cấm kết hôn theo quy định của pháp luật [E1].
>
> Trong trường hợp kết hôn có yếu tố nước ngoài, mỗi bên phải tuân theo pháp luật của nước mình về điều kiện kết hôn. Nếu việc kết hôn được tiến hành tại cơ quan nhà nước có thẩm quyền của Việt Nam, người nước ngoài còn phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E3]. Tương tự, việc kết hôn giữa những người nước ngoài thường trú tại Việt N...

### Citation Summaries

- Not available in the Phase 9C.1 report. Inspect the selected evidence and record the legal hierarchy, source, and supporting text here.

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Điều kiện kết hôn theo pháp luật Việt Nam bao gồm: | none | unchecked | |
| Nam và nữ kết hôn với nhau phải do cả hai tự nguyện quyết định [E2]. | [E2] | unchecked | |
| Việc kết hôn không thuộc các trường hợp cấm kết hôn theo quy định của pháp luật [E1]. | [E1] | unchecked | |
| Trong trường hợp kết hôn có yếu tố nước ngoài, mỗi bên phải tuân theo pháp luật của nước mình về điều kiện kết hôn. | none | unchecked | |
| Nếu việc kết hôn được tiến hành tại cơ quan nhà nước có thẩm quyền của Việt Nam, người nước ngoài còn phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E3]. | [E3] | unchecked | |
| Tương tự, việc kết hôn giữa những người nước ngoài thường trú tại Việt N... | none | unchecked | |

### Manual Review Checklist

- [ ] Every material legal claim is supported by its cited evidence.
- [ ] Citation hierarchy and source metadata match the claim.
- [ ] The answer does not broaden conditions, exceptions, or scope.
- [ ] Caution evidence has been inspected and explained.
- [ ] Auxiliary context was not treated as directly citable evidence.
- [ ] Final verdict and reviewer notes are recorded.

Reviewer notes:

> Unchecked.

## 5. `civil_rights_protection_generation`

- Query: Quyền dân sự được công nhận và bảo vệ như thế nào?
- Decision: `answer_allowed`
- LLM called: `true`
- Blocking: `false`
- Manual review required: `true`
- Selected evidence count: 5
- Caution selected count: 2
- All selected evidence caution: `false`
- Cited evidence IDs in preview: [E1], [E2], [E4], [E5]
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`

### Answer Preview

> Quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm theo Hiến pháp và pháp luật tại Việt Nam [E1]. Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật trong trường hợp cần thiết vì lý do quốc phòng, an ninh quốc gia, trật tự, an toàn xã hội, đạo đức xã hội, hoặc sức khỏe của cộng đồng [E2]. Pháp luật bảo hộ tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản của cá nhân [E4]. Cơ quan, người có thẩm quyền tiến hành tố tụng phải tôn trọng và bảo vệ quyền con người, quyền và lợi ích hợp pháp của cá nhân [E5].

### Citation Summaries

- Not available in the Phase 9C.1 report. Inspect the selected evidence and record the legal hierarchy, source, and supporting text here.

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm theo Hiến pháp và pháp luật tại Việt Nam [E1]. | [E1] | unchecked | |
| Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật trong trường hợp cần thiết vì lý do quốc phòng, an ninh quốc gia, trật tự, an toàn xã hội, đạo đức xã hội, hoặc sức khỏe của cộng đồng [E2]. | [E2] | unchecked | |
| Pháp luật bảo hộ tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản của cá nhân [E4]. | [E4] | unchecked | |
| Cơ quan, người có thẩm quyền tiến hành tố tụng phải tôn trọng và bảo vệ quyền con người, quyền và lợi ích hợp pháp của cá nhân [E5]. | [E5] | unchecked | |

### Manual Review Checklist

- [ ] Every material legal claim is supported by its cited evidence.
- [ ] Citation hierarchy and source metadata match the claim.
- [ ] The answer does not broaden conditions, exceptions, or scope.
- [ ] Caution evidence has been inspected and explained.
- [ ] Auxiliary context was not treated as directly citable evidence.
- [ ] Final verdict and reviewer notes are recorded.

Reviewer notes:

> Unchecked.
