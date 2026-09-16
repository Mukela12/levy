import AppKit
import Foundation
import Vision

struct RecognizedLine: Codable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct PageResult: Codable {
    let path: String
    let lines: [RecognizedLine]
}

func recognize(_ path: String) throws -> PageResult {
    guard
        let image = NSImage(contentsOfFile: path),
        let tiff = image.tiffRepresentation,
        let bitmap = NSBitmapImageRep(data: tiff),
        let cgImage = bitmap.cgImage
    else {
        throw NSError(domain: "LevyVisionOCR", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "cannot decode image: \(path)"])
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-GB"]
    request.minimumTextHeight = 0.004

    try VNImageRequestHandler(cgImage: cgImage).perform([request])
    let lines = (request.results ?? []).compactMap { observation -> RecognizedLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return RecognizedLine(
            text: candidate.string,
            confidence: candidate.confidence,
            x: box.minX,
            y: box.minY,
            width: box.width,
            height: box.height
        )
    }.sorted { left, right in
        if abs(left.y + left.height - right.y - right.height) > 0.008 {
            return left.y + left.height > right.y + right.height
        }
        return left.x < right.x
    }
    return PageResult(path: path, lines: lines)
}

let encoder = JSONEncoder()
for path in CommandLine.arguments.dropFirst() {
    autoreleasepool {
        do {
            let result = try recognize(path)
            let data = try encoder.encode(result)
            print(String(decoding: data, as: UTF8.self))
        } catch {
            FileHandle.standardError.write(Data("\(path): \(error)\n".utf8))
            exit(1)
        }
    }
}
