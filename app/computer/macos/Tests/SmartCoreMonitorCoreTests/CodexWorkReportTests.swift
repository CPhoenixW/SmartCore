import Foundation
import SmartCoreMonitorCore
import Testing

@Test func codexWorkReportBatchDecodesTheScheduledPayload() throws {
    let data = Data(
        #"""
        {
          "reports": [{
            "sourceTaskId": "thread-1",
            "reportDate": "2026-07-29",
            "timezone": "Asia/Shanghai",
            "projectKey": "smartcore",
            "projectName": "SmartCore",
            "title": "完善工作分析",
            "summary": "完成工作块接口并通过后端测试。",
            "status": "completed",
            "startedAt": "2026-07-29T09:00:00+08:00",
            "endedAt": "2026-07-29T11:00:00+08:00",
            "evidence": {
              "commits": ["abc123"],
              "pullRequests": [],
              "tests": ["pytest"]
            }
          }]
        }
        """#.utf8
    )

    let batch = try MonitorCoding.decoder().decode(CodexWorkReportBatch.self, from: data)

    #expect(batch.reports.count == 1)
    #expect(batch.reports[0].projectName == "SmartCore")
    #expect(batch.reports[0].status == .completed)
    #expect(batch.reports[0].evidence.tests == ["pytest"])
}

@Test func codexWorkReportBatchEncodesServerFieldNames() throws {
    let report = CodexWorkReport(
        sourceTaskId: "thread-2",
        reportDate: "2026-07-29",
        timezone: "Asia/Shanghai",
        projectKey: "paper-act",
        projectName: "ACT Paper",
        title: "继续阅读论文",
        summary: "完成方法部分阅读，实验部分仍在进行。",
        status: .inProgress
    )

    let data = try MonitorCoding.encoder().encode(CodexWorkReportBatch(reports: [report]))
    let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let rows = try #require(object["reports"] as? [[String: Any]])

    #expect(rows[0]["status"] as? String == "in_progress")
    #expect(rows[0]["sourceTaskId"] as? String == "thread-2")
}
