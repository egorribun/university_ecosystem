import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test.describe("Malicious upload rejection", () => {
  test("displays ClamAV warning message when scanner rejects infected file", async ({ page }) => {
    const mock = await useMockApi(page)

    // Make user an admin so they can access the upload files section
    mock.state.profile.role = "admin"
    await mock.login(page)

    // Intercept event files upload and simulate malware scanner failure
    // The CI API base is `http://api`, while local runs may use `/api/v1` on
    // the preview origin. Matching the shared `/v1/...` suffix supports both.
    await page.context().route("**/v1/events/*/upload_file", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Файл содержит вредоносное содержимое" }),
      })
    })

    // Navigate to event details page
    await page.goto("/events/uuid-10")
    await page.waitForURL(/\/events\/uuid-10$/)

    // Locate file input and set a dummy file
    const fileInput = page.locator('input[type="file"]')
    await expect(fileInput).toBeAttached()
    await fileInput.setInputFiles({
      name: "eicar.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"),
    })

    // Click the submit button
    const submitBtn = page.getByRole("button", { name: /Добавить/i })
    await expect(submitBtn).toBeEnabled()
    await submitBtn.click()

    // Assert that the exact malware rejection error is shown in a toast/snackbar
    await expect(page.getByText("Файл содержит вредоносное содержимое")).toBeVisible({
      timeout: 10000,
    })
  })
})
