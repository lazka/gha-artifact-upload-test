import { validateArtifactName } from '@actions/artifact/lib/internal/upload/path-and-artifact-name-validation.js'
import { internalArtifactTwirpClient } from '@actions/artifact/lib/internal/shared/artifact-twirp-client.js'
import { getBackendIdsFromToken } from '@actions/artifact/lib/internal/shared/util.js'
import { getExpiration } from '@actions/artifact/lib/internal/upload/retention.js'
import { createRawFileUploadStream } from '@actions/artifact/lib/internal/upload/stream.js'
import { uploadToBlobStorage } from '@actions/artifact/lib/internal/upload/blob-upload.js'
import { getMimeType } from '@actions/artifact/lib/internal/upload/types.js'
import { StringValue, Timestamp } from '@actions/artifact/lib/generated/index.js'
import { InvalidResponseError } from '@actions/artifact/lib/internal/shared/errors.js'

const ERROR_PREFIX = 'GHA_ARTIFACT_CLIENT_ERROR:'

/**
 * @typedef {{
 *   action: 'upload',
 *   name: string,
 *   filePath: string,
 *   mimeType?: string,
 *   retentionDays?: number,
 *   expiresAt?: number,
 * }} UploadPayload
 */

/**
 * @typedef {{
 *   action: 'delete',
 *   name: string,
 * }} DeletePayload
 */

/**
 * @typedef {{
 *   action: 'get-signed-url',
 *   name: string,
 * }} GetSignedUrlPayload
 */

/**
 * @typedef {{
 *   action: 'list',
 * }} ListPayload
 */

/**
 * @typedef {{
 *   id: string,
 *   name: string,
 *   size: string,
 *   createdAt: string,
 *   digest: string,
 * }} ListArtifactInfo
 */

/**
 * @typedef {UploadPayload | DeletePayload | GetSignedUrlPayload | ListPayload} Payload
 */

/**
 * @typedef {{
 *   error: string,
 *   message: string,
 * }} ErrorDetails
 */

/**
 * @returns {Promise<string>}
 */
function readStdin() {
  return new Promise((resolve, reject) => {
    let data = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', chunk => {
      data += chunk
    })
    process.stdin.on('end', () => {
      resolve(data)
    })
    process.stdin.on('error', reject)
  })
}

/**
 * @template T
 * @param {() => Promise<T>} fn
 * @returns {Promise<T>}
 */
async function withStdoutRedirect(fn) {
  const originalWrite = process.stdout.write.bind(process.stdout)
  const redirectedWrite = /** @type {typeof originalWrite} */ (...args) =>
    Reflect.apply(process.stderr.write, process.stderr, args)
  process.stdout.write = redirectedWrite

  try {
    return await fn()
  } finally {
    process.stdout.write = originalWrite
  }
}

/**
 * @param {UploadPayload} payload
 * @returns {Promise<{size: number, digest: string, id: string}>}
 */
async function uploadArtifact(payload) {
  const { name, filePath, mimeType, retentionDays, expiresAt } = payload

  validateArtifactName(name)

  const contentType = mimeType ?? getMimeType(filePath)

  const backendIds = getBackendIdsFromToken()
  const artifactClient = internalArtifactTwirpClient()

  /** @type {import('@actions/artifact/lib/generated/results/api/v1/artifact.js').CreateArtifactRequest} */
  const createArtifactReq = {
    workflowRunBackendId: backendIds.workflowRunBackendId,
    workflowJobRunBackendId: backendIds.workflowJobRunBackendId,
    name,
    mimeType: StringValue.create({ value: contentType }),
    version: 7,
  }

  let expires
  if (expiresAt !== undefined) {
    expires = Timestamp.fromDate(new Date(expiresAt * 1000))
  } else {
    expires = getExpiration(retentionDays)
  }
  if (expires !== undefined) {
    createArtifactReq.expiresAt = expires
  }

  const createArtifactResp = await artifactClient.CreateArtifact(createArtifactReq)
  if (!createArtifactResp.ok) {
    throw new InvalidResponseError('CreateArtifact: response from backend was not ok')
  }

  const stream = await createRawFileUploadStream(filePath)
  const uploadResult = await uploadToBlobStorage(
    createArtifactResp.signedUploadUrl,
    stream,
    contentType
  )

  if (uploadResult.uploadSize === undefined) {
    throw new Error('uploadToBlobStorage did not return uploadSize')
  }
  if (!uploadResult.sha256Hash) {
    throw new Error('uploadToBlobStorage did not return sha256Hash')
  }

  /** @type {import('@actions/artifact/lib/generated/results/api/v1/artifact.js').FinalizeArtifactRequest} */
  const finalizeArtifactReq = {
    workflowRunBackendId: backendIds.workflowRunBackendId,
    workflowJobRunBackendId: backendIds.workflowJobRunBackendId,
    name,
    size: uploadResult.uploadSize.toString(),
    hash: StringValue.create({ value: `sha256:${uploadResult.sha256Hash}` }),
  }

  const finalizeArtifactResp = await artifactClient.FinalizeArtifact(finalizeArtifactReq)
  if (!finalizeArtifactResp.ok) {
    throw new InvalidResponseError('FinalizeArtifact: response from backend was not ok')
  }

  if (!finalizeArtifactResp.artifactId) {
    throw new Error('FinalizeArtifact: response did not return artifactId')
  }

  return {
    size: uploadResult.uploadSize,
    digest: `sha256:${uploadResult.sha256Hash}`,
    id: finalizeArtifactResp.artifactId,
  }
}

/**
 * @param {DeletePayload} payload
 * @returns {Promise<{id: number}>}
 */
async function deleteArtifact(payload) {
  const { name } = payload

  const backendIds = getBackendIdsFromToken()
  const artifactClient = internalArtifactTwirpClient()

  /** @type {import('@actions/artifact/lib/generated/results/api/v1/artifact.js').DeleteArtifactRequest} */
  const deleteArtifactReq = {
    workflowRunBackendId: backendIds.workflowRunBackendId,
    workflowJobRunBackendId: backendIds.workflowJobRunBackendId,
    name,
  }

  const deleteArtifactResp = await artifactClient.DeleteArtifact(deleteArtifactReq)
  if (!deleteArtifactResp.ok) {
    throw new InvalidResponseError('DeleteArtifact: response from backend was not ok')
  }

  return { id: Number(deleteArtifactResp.artifactId) }
}

/**
 * @param {GetSignedUrlPayload} payload
 * @returns {Promise<{url: string}>}
 */
async function getSignedUrl(payload) {
  const { name } = payload

  const backendIds = getBackendIdsFromToken()
  const artifactClient = internalArtifactTwirpClient()

  /** @type {import('@actions/artifact/lib/generated/results/api/v1/artifact.js').GetSignedArtifactURLRequest} */
  const getSignedUrlReq = {
    workflowRunBackendId: backendIds.workflowRunBackendId,
    workflowJobRunBackendId: backendIds.workflowJobRunBackendId,
    name,
  }

  const getSignedUrlResp = await artifactClient.GetSignedArtifactURL(getSignedUrlReq)
  if (!getSignedUrlResp.signedUrl) {
    throw new InvalidResponseError('GetSignedArtifactURL: response did not return signedUrl')
  }

  return { url: getSignedUrlResp.signedUrl }
}

/**
 * @param {ListPayload} payload
 * @returns {Promise<{artifacts: Array<ListArtifactInfo>}>}
 */
async function listArtifacts(payload) {
  void payload

  const backendIds = getBackendIdsFromToken()
  const artifactClient = internalArtifactTwirpClient()

  /** @type {import('@actions/artifact/lib/generated/results/api/v1/artifact.js').ListArtifactsRequest} */
  const listArtifactsReq = {
    workflowRunBackendId: backendIds.workflowRunBackendId,
    workflowJobRunBackendId: backendIds.workflowJobRunBackendId,
  }

  const listArtifactsResp = await artifactClient.ListArtifacts(listArtifactsReq)

  const artifacts = listArtifactsResp.artifacts.map(artifact => {
    const createdAtDate = artifact.createdAt
      ? Timestamp.toDate(artifact.createdAt)
      : null
    const digest = artifact.digest?.value ?? null

    if (!createdAtDate) {
      throw new InvalidResponseError(
        `ListArtifacts: artifact '${artifact.name}' is missing createdAt`
      )
    }
    if (!digest) {
      throw new InvalidResponseError(
        `ListArtifacts: artifact '${artifact.name}' is missing digest`
      )
    }

    return {
      id: String(artifact.databaseId),
      name: artifact.name,
      size: String(artifact.size),
      createdAt: String(createdAtDate.getTime()),
      digest,
    }
  })

  return { artifacts }
}

async function main() {
  try {
    const payload = /** @type {Payload} */ (JSON.parse(await readStdin()))

    if (payload.action === 'delete') {
      const response = await withStdoutRedirect(() => deleteArtifact(payload))
      process.stdout.write(`${JSON.stringify(response)}\n`)
    } else if (payload.action === 'get-signed-url') {
      const response = await withStdoutRedirect(() => getSignedUrl(payload))
      process.stdout.write(`${JSON.stringify(response)}\n`)
    } else if (payload.action === 'list') {
      const response = await withStdoutRedirect(() => listArtifacts(payload))
      process.stdout.write(`${JSON.stringify(response)}\n`)
    } else if (payload.action === 'upload') {
      const response = await withStdoutRedirect(() => uploadArtifact(payload))
      process.stdout.write(`${JSON.stringify(response)}\n`)
    } else {
      throw new Error(`Unknown action: ${/** @type {{action: unknown}} */ (payload).action}`)
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const details = /** @type {ErrorDetails} */ ({
      error: error instanceof Error ? error.name : 'Error',
      message,
    })

    process.stderr.write(`${ERROR_PREFIX}${JSON.stringify(details)}\n`)
    process.exitCode = 1
  }
}

await main()
