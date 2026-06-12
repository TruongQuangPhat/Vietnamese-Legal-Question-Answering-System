# Naive RAG Manual Faithfulness Review

Status: `evidence_preview_review_ready`

This worksheet supports human claim-to-citation inspection. It does not prove semantic faithfulness or legal correctness and is not professional legal advice.

Evidence previews contain only short, redacted safe-citable child text. Auxiliary parent context is represented by flags and is not directly citable. Reviewers must still assign all semantic verdicts manually.

## Run Summary

- Source status: `expanded_generation_eval_passed`
- Cases: 5
- Generated answers: 4
- Fallback cases: 1
- Manual-review cases: 2
- All-caution cases: 2
- Evidence previews: 20
- Missing cited evidence previews: 0
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
- Evidence preview count: 5
- Missing cited evidence previews: 0
- Answer truncated: `false`
- Priority flags: all-caution evidence
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

> Trẻ em dưới 6 tuổi là một trong những đối tượng được tham gia bảo hiểm y tế [E3].
>
> Về thời hạn sử dụng thẻ bảo hiểm y tế:
> *   Thẻ bảo hiểm y tế có giá trị sử dụng đến ngày trẻ đủ 72 tháng tuổi [E1].
> *   Nếu trẻ đủ 72 tháng tuổi mà chưa đến kỳ nhập học, thẻ bảo hiểm y tế có giá trị sử dụng đến ngày 30 tháng 9 của năm đó [E1].
>
> Về thủ tục khám bệnh, chữa bệnh:
> *   Khi khám bệnh, chữa bệnh, trẻ em dưới 6 tuổi chưa được cấp thẻ bảo hiểm y tế phải xuất trình giấy tờ hợp pháp khác [E2].
> *   Trường hợp cấp cứu, người bệnh phải xuất trình thông tin về thẻ bảo hiểm y tế, giấy tờ hợp pháp khác trước khi kết thúc đợt điều trị [E2].

### Evidence Preview Table

| Evidence ID | Citation | Scope | Safety | Text Preview | Source |
| --- | --- | --- | --- | --- | --- |
| E1 | Luật Bảo hiểm y tế (VBHN 2025), Điểm d, Khoản 3, Điều 16 | unsafe_parent_context | caution | d) Đối với trẻ em dưới 6 tuổi thì thẻ bảo hiểm y tế có giá trị sử dụng đến ngày trẻ đủ 72 tháng tuổi. Trường hợp trẻ đủ 72 tháng tuổi mà chưa đến kỳ nhập học thì thẻ bảo hiểm y tế có giá trị sử dụng đến ngày 30 tháng 9 của năm đó. | https://thuvienphapluat.vn/van-ban/Bao-hiem/Van-ban-hop-nhat-22-VBHN-VPQH-2025-Luat-Bao-hiem-y-te-651354.aspx |
| E2 | Luật Bảo hiểm y tế (VBHN 2025), Khoản 1, Điều 28 | unsafe_parent_context | caution | 1. Người tham gia bảo hiểm y tế khi khám bệnh, chữa bệnh phải xuất trình thông tin về thẻ bảo hiểm y tế, giấy tờ chứng minh nhân thân của người đó; trẻ em dưới 6 tuổi và người đã hiến bộ phận cơ thể người chưa được cấp thẻ bảo hiểm y tế thì xuất trình giấy tờ hợp pháp khác. Trường hợp cấp cứu, người bệnh phải xuất trình thông tin về thẻ bảo hiểm y tế, giấy tờ theo quy định tại khoản này trước khi kết thúc đợt điều trị. Chính phủ quy định chi tiết khoản này. | https://thuvienphapluat.vn/van-ban/Bao-hiem/Van-ban-hop-nhat-22-VBHN-VPQH-2025-Luat-Bao-hiem-y-te-651354.aspx |
| E3 | Luật Bảo hiểm y tế (VBHN 2025), Điểm h, Khoản 3, Điều 12 | unsafe_parent_context | caution | h) Trẻ em dưới 6 tuổi; | https://thuvienphapluat.vn/van-ban/Bao-hiem/Van-ban-hop-nhat-22-VBHN-VPQH-2025-Luat-Bao-hiem-y-te-651354.aspx |
| E4 | Luật Bảo hiểm xã hội (VBHN 2026), Khoản 6, Điều 23 | unsafe_parent_context | caution | 6. Người đang trong thời gian hưởng trợ cấp hằng tháng thì được ngân sách nhà nước đóng bảo hiểm y tế. | https://thuvienphapluat.vn/van-ban/Bao-hiem/Van-ban-hop-nhat-19-VBHN-VPQH-2026-Luat-Bao-hiem-xa-hoi-696579.aspx |
| E5 | Luật Bảo hiểm y tế (VBHN 2025), Khoản 6, Điều 15 | unsafe_parent_context | caution | 6. Định kỳ 3 tháng, 6 tháng hoặc 12 tháng, đại diện hộ gia đình, tổ chức, cá nhân đóng đủ số tiền thuộc trách nhiệm phải đóng vào quỹ bảo hiểm y tế. | https://thuvienphapluat.vn/van-ban/Bao-hiem/Van-ban-hop-nhat-22-VBHN-VPQH-2025-Luat-Bao-hiem-y-te-651354.aspx |

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Trẻ em dưới 6 tuổi là một trong những đối tượng được tham gia bảo hiểm y tế [E3]. | [E3] | unchecked | |
| Về thời hạn sử dụng thẻ bảo hiểm y tế: | none | unchecked | |
| Thẻ bảo hiểm y tế có giá trị sử dụng đến ngày trẻ đủ 72 tháng tuổi [E1]. | [E1] | unchecked | |
| Nếu trẻ đủ 72 tháng tuổi mà chưa đến kỳ nhập học, thẻ bảo hiểm y tế có giá trị sử dụng đến ngày 30 tháng 9 của năm đó [E1]. | [E1] | unchecked | |
| Về thủ tục khám bệnh, chữa bệnh: | none | unchecked | |
| Khi khám bệnh, chữa bệnh, trẻ em dưới 6 tuổi chưa được cấp thẻ bảo hiểm y tế phải xuất trình giấy tờ hợp pháp khác [E2]. | [E2] | unchecked | |
| Trường hợp cấp cứu, người bệnh phải xuất trình thông tin về thẻ bảo hiểm y tế, giấy tờ hợp pháp khác trước khi kết thúc đợt điều trị [E2]. | [E2] | unchecked | |

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
- Evidence preview count: 0
- Missing cited evidence previews: 0
- Answer truncated: `false`
- Priority flags: fallback case
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

### Evidence Preview Table

| Evidence ID | Citation | Scope | Safety | Text Preview | Source |
| --- | --- | --- | --- | --- | --- |
| none | unavailable | unavailable | unavailable | missing preview | |

### Fallback Review

| Check | Recorded state | Reviewer check | Notes |
| --- | --- | --- | --- |
| Fallback decision recorded | `fallback_required` | checked | |
| LLM was not called | `true` | checked | |
| Citation count is zero | `true` | checked | |
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
- Evidence preview count: 5
- Missing cited evidence previews: 0
- Answer truncated: `false`
- Priority flags: none
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- None recorded.

### Answer Preview

> Bộ luật Dân sự quy định về địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm [E1]. Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương khi tham gia quan hệ dân sự thì bình đẳng với các chủ thể khác và chịu trách nhiệm dân sự [E5].

### Evidence Preview Table

| Evidence ID | Citation | Scope | Safety | Text Preview | Source |
| --- | --- | --- | --- | --- | --- |
| E1 | Bộ luật Dân sự 2015, Điều 1 | article_context | safe | Điều 1. Phạm vi điều chỉnh Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm (sau đây gọi chung là quan hệ dân sự). | https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx |
| E2 | Luật Hôn nhân và gia đình (VBHN 2025), Điều 6 | article_context | safe | Điều 6. Áp dụng quy định của Bộ luật dân sự và các luật khác có liên quan Các quy định của Bộ luật dân sự và các luật khác có liên quan đến quan hệ hôn nhân và gia đình được áp dụng đối với quan hệ hôn nhân và gia đình trong trường hợp Luật này không quy định. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E3 | Bộ luật Tố tụng dân sự (VBHN 2025), Điều 1 | article_context | safe | Điều 1. Phạm vi điều chỉnh và nhiệm vụ của Bộ luật Tố tụng dân sự Bộ luật Tố tụng dân sự quy định những nguyên tắc cơ bản trong tố tụng dân sự; trình tự, thủ tục khởi kiện để Tòa án nhân dân (sau đây gọi là Tòa án) giải quyết các vụ án về tranh chấp dân sự, hôn nhân và gia đình, kinh doanh, thương mại, lao động (sau đây gọi chung là vụ án dân sự) và trình tự, thủ tục yêu cầu để Tòa án giải quyết các việc về yêu cầu dân sự, hôn nhân và gia đình, kinh doanh, thương mại, lao động (sau đây gọi chung... [truncated] | https://thuvienphapluat.vn/van-ban/Thu-tuc-To-tung/Van-ban-hop-nhat-99-VBHN-VPQH-2025-Bo-luat-To-tung-dan-su-672478.aspx |
| E4 | Luật Hôn nhân và gia đình (VBHN 2025), Điều 1 | article_context | safe | Điều 1. Phạm vi điều chỉnh Luật này quy định chế độ hôn nhân và gia đình; chuẩn mực pháp lý cho cách ứng xử giữa các thành viên gia đình; trách nhiệm của cá nhân, tổ chức, Nhà nước và xã hội trong việc xây dựng, củng cố chế độ hôn nhân và gia đình. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E5 | Bộ luật Dân sự 2015, Điều 97 | article_context | safe | Điều 97. Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương trong quan hệ dân sự Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương khi tham gia quan hệ dân sự thì bình đẳng với các chủ thể khác và chịu trách nhiệm dân sự theo quy định tại Điều 99 và Điều 100 của Bộ luật này. | https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx |

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Bộ luật Dân sự quy định về địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm [E1]. | [E1] | unchecked | |
| Nhà nước Cộng hòa xã hội chủ nghĩa Việt Nam, cơ quan nhà nước ở Trung ương, ở địa phương khi tham gia quan hệ dân sự thì bình đẳng với các chủ thể khác và chịu trách nhiệm dân sự [E5]. | [E5] | unchecked | |

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
- Cited evidence IDs in preview: [E2], [E1], [E3], [E5], [E4]
- Evidence preview count: 5
- Missing cited evidence previews: 0
- Answer truncated: `false`
- Priority flags: all-caution evidence, manual-review required
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
> Trong trường hợp kết hôn có yếu tố nước ngoài, mỗi bên phải tuân theo pháp luật của nước mình về điều kiện kết hôn. Nếu việc kết hôn được tiến hành tại cơ quan nhà nước có thẩm quyền của Việt Nam, người nước ngoài còn phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E3]. Tương tự, việc kết hôn giữa những người nước ngoài thường trú tại Việt Nam tại cơ quan có thẩm quyền của Việt Nam cũng phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E5].
>
> Kết hôn được định nghĩa là việc nam và nữ xác lập quan hệ vợ chồng với nhau theo quy định của Luật này về điều kiện kết hôn và đăng ký kết hôn [E4].

### Evidence Preview Table

| Evidence ID | Citation | Scope | Safety | Text Preview | Source |
| --- | --- | --- | --- | --- | --- |
| E1 | Luật Hôn nhân và gia đình (VBHN 2025), Điểm d, Khoản 1, Điều 8 | unsafe_parent_context | caution | d) Việc kết hôn không thuộc một trong các trường hợp cấm kết hôn theo quy định tại các điểm a, b, c và d khoản 2 Điều 5 của Luật này. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E2 | Luật Hôn nhân và gia đình (VBHN 2025), Điểm b, Khoản 1, Điều 8 | unsafe_parent_context | caution | b) Việc kết hôn do nam và nữ tự nguyện quyết định; | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E3 | Luật Hôn nhân và gia đình (VBHN 2025), Khoản 1, Điều 126 | unsafe_parent_context | caution | 1. Trong việc kết hôn giữa công dân Việt Nam với người nước ngoài, mỗi bên phải tuân theo pháp luật của nước mình về điều kiện kết hôn; nếu việc kết hôn được tiến hành tại cơ quan nhà nước có thẩm quyền của Việt Nam thì người nước ngoài còn phải tuân theo các quy định của Luật này về điều kiện kết hôn. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E4 | Luật Hôn nhân và gia đình (VBHN 2025), Khoản 5, Điều 3 | unsafe_parent_context | caution | 5. Kết hôn là việc nam và nữ xác lập quan hệ vợ chồng với nhau theo quy định của Luật này về điều kiện kết hôn và đăng ký kết hôn. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |
| E5 | Luật Hôn nhân và gia đình (VBHN 2025), Khoản 2, Điều 126 | unsafe_parent_context | caution | 2. Việc kết hôn giữa những người nước ngoài thường trú ở Việt Nam tại cơ quan có thẩm quyền của Việt Nam phải tuân theo các quy định của Luật này về điều kiện kết hôn. | https://thuvienphapluat.vn/van-ban/Van-hoa-Xa-hoi/Van-ban-hop-nhat-121-VBHN-VPQH-2025-Luat-Hon-nhan-va-gia-dinh-672447.aspx |

### Claim-to-Citation Checklist

| Claim from answer preview | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| Điều kiện kết hôn theo pháp luật Việt Nam bao gồm: | none | unchecked | |
| Nam và nữ kết hôn với nhau phải do cả hai tự nguyện quyết định [E2]. | [E2] | unchecked | |
| Việc kết hôn không thuộc các trường hợp cấm kết hôn theo quy định của pháp luật [E1]. | [E1] | unchecked | |
| Trong trường hợp kết hôn có yếu tố nước ngoài, mỗi bên phải tuân theo pháp luật của nước mình về điều kiện kết hôn. | none | unchecked | |
| Nếu việc kết hôn được tiến hành tại cơ quan nhà nước có thẩm quyền của Việt Nam, người nước ngoài còn phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E3]. | [E3] | unchecked | |
| Tương tự, việc kết hôn giữa những người nước ngoài thường trú tại Việt Nam tại cơ quan có thẩm quyền của Việt Nam cũng phải tuân theo các quy định của Luật Hôn nhân và gia đình Việt Nam về điều kiện kết hôn [E5]. | [E5] | unchecked | |
| Kết hôn được định nghĩa là việc nam và nữ xác lập quan hệ vợ chồng với nhau theo quy định của Luật này về điều kiện kết hôn và đăng ký kết hôn [E4]. | [E4] | unchecked | |

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
- Evidence preview count: 5
- Missing cited evidence previews: 0
- Answer truncated: `false`
- Priority flags: manual-review required
- Fallback reasons: none
- Preliminary reviewer verdict: `unchecked`

### Selection Warnings

- `caution_evidence_selected`
- `auxiliary_parent_context_included`
- `caution_evidence_selected`

### Answer Preview

> Quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm theo Hiến pháp và pháp luật tại Việt Nam [E1]. Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật trong trường hợp cần thiết vì lý do quốc phòng, an ninh quốc gia, trật tự, an toàn xã hội, đạo đức xã hội, hoặc sức khỏe của cộng đồng [E2]. Pháp luật bảo hộ tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản của cá nhân [E4]. Cơ quan, người có thẩm quyền tiến hành tố tụng phải tôn trọng và bảo vệ quyền con người, quyền và lợi ích hợp pháp của cá nhân [E5].

### Evidence Preview Table

| Evidence ID | Citation | Scope | Safety | Text Preview | Source |
| --- | --- | --- | --- | --- | --- |
| E1 | Bộ luật Dân sự 2015, Khoản 1, Điều 2 | unsafe_parent_context | caution | 1. Ở nước Cộng hòa xã hội chủ nghĩa Việt Nam, các quyền dân sự được công nhận, tôn trọng, bảo vệ và bảo đảm theo Hiến pháp và pháp luật. | https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx |
| E2 | Bộ luật Dân sự 2015, Khoản 2, Điều 2 | unsafe_parent_context | caution | 2. Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật trong trường hợp cần thiết vì lý do quốc phòng, an ninh quốc gia, trật tự, an toàn xã hội, đạo đức xã hội, sức khỏe của cộng đồng. | https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx |
| E3 | Bộ luật Tố tụng dân sự (VBHN 2025), Điều 361 | article_context | safe | Điều 361. Phạm vi áp dụng Việc dân sự là việc cơ quan, tổ chức, cá nhân không có tranh chấp, nhưng có yêu cầu Tòa án công nhận hoặc không công nhận một sự kiện pháp lý là căn cứ làm phát sinh quyền, nghĩa vụ dân sự, hôn nhân và gia đình, kinh doanh, thương mại, lao động của mình hoặc của cơ quan, tổ chức, cá nhân khác; yêu cầu Tòa án công nhận cho mình quyền về dân sự, hôn nhân và gia đình, kinh doanh, thương mại, lao động. Những quy định của Phần này được áp dụng để giải quyết việc dân sự quy đ... [truncated] | https://thuvienphapluat.vn/van-ban/Thu-tuc-To-tung/Van-ban-hop-nhat-99-VBHN-VPQH-2025-Bo-luat-To-tung-dan-su-672478.aspx |
| E4 | Bộ luật Tố tụng hình sự (VBHN 2025), Điều 11 | article_context | safe | Điều 11. Bảo hộ tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản của cá nhân; danh dự, uy tín, tài sản của pháp nhân Mọi người có quyền được pháp luật bảo hộ về tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản. Mọi hành vi xâm phạm trái pháp luật tính mạng, sức khỏe, danh dự, nhân phẩm, tài sản của cá nhân; xâm phạm danh dự, uy tín, tài sản của pháp nhân đều bị xử lý theo pháp luật. Công dân Việt Nam không thể bị trục xuất, giao nộp cho nhà nước khác. | https://thuvienphapluat.vn/van-ban/Thu-tuc-To-tung/Van-ban-hop-nhat-46-VBHN-VPQH-2025-Bo-Luat-To-tung-hinh-su-647146.aspx |
| E5 | Bộ luật Tố tụng hình sự (VBHN 2025), Điều 8 | article_context | safe | Điều 8. Tôn trọng và bảo vệ quyền con người, quyền và lợi ích hợp pháp của cá nhân Khi tiến hành tố tụng, trong phạm vi nhiệm vụ, quyền hạn của mình, cơ quan, người có thẩm quyền tiến hành tố tụng phải tôn trọng và bảo vệ quyền con người, quyền và lợi ích hợp pháp của cá nhân; thường xuyên kiểm tra tính hợp pháp và sự cần thiết của những biện pháp đã áp dụng, kịp thời hủy bỏ hoặc thay đổi những biện pháp đó nếu xét thấy có vi phạm pháp luật hoặc không còn cần thiết. | https://thuvienphapluat.vn/van-ban/Thu-tuc-To-tung/Van-ban-hop-nhat-46-VBHN-VPQH-2025-Bo-Luat-To-tung-hinh-su-647146.aspx |

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
