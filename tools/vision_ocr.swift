import AppKit
import Foundation
import PDFKit
import Vision

func usage() -> Never {
    FileHandle.standardError.write(Data("usage: vision_ocr.swift PDF [scale]\n".utf8))
    exit(2)
}

guard CommandLine.arguments.count >= 2 else { usage() }
let input = CommandLine.arguments[1]
let scale = CommandLine.arguments.count >= 3 ? CGFloat(Double(CommandLine.arguments[2]) ?? 2.0) : 2.0
let requestedLanguage = CommandLine.arguments.count >= 4 ? CommandLine.arguments[3] : "auto"

guard let document = PDFDocument(url: URL(fileURLWithPath: input)) else {
    FileHandle.standardError.write(Data("cannot open PDF: \(input)\n".utf8))
    exit(1)
}

let supported = (try? VNRecognizeTextRequest.supportedRecognitionLanguages(
    for: .accurate,
    revision: VNRecognizeTextRequestRevision3
)) ?? []
let preferred = ["is-IS", "en-US", "de-DE", "it-IT", "sv-SE", "da-DK", "nb-NO"]
let languages = requestedLanguage == "auto"
    ? preferred.filter(supported.contains)
    : [requestedLanguage].filter(supported.contains)

for pageIndex in 0..<document.pageCount {
    guard let page = document.page(at: pageIndex) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let width = max(1, Int(ceil(bounds.width * scale)))
    let height = max(1, Int(ceil(bounds.height * scale)))
    guard let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { continue }

    context.setFillColor(NSColor.white.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.saveGState()
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: context)
    context.restoreGState()
    guard let image = context.makeImage() else { continue }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.revision = VNRecognizeTextRequestRevision3
    if !languages.isEmpty { request.recognitionLanguages = languages }

    do {
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        let observations = (request.results ?? []).sorted {
            if abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.010 {
                return $0.boundingBox.midY > $1.boundingBox.midY
            }
            return $0.boundingBox.minX < $1.boundingBox.minX
        }
        var rows: [[VNRecognizedTextObservation]] = []
        for observation in observations {
            if let index = rows.indices.last,
               let anchor = rows[index].first,
               abs(anchor.boundingBox.midY - observation.boundingBox.midY) <= 0.010 {
                rows[index].append(observation)
            } else {
                rows.append([observation])
            }
        }
        for row in rows {
            let text = row.sorted { $0.boundingBox.minX < $1.boundingBox.minX }
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: " ")
            if !text.isEmpty { print(text) }
        }
    } catch {
        FileHandle.standardError.write(Data("page \(pageIndex + 1): \(error)\n".utf8))
    }
    if pageIndex + 1 < document.pageCount { print("\u{000C}") }
}
