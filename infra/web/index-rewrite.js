// CloudFront Function (viewer-request, cloudfront-js-2.0).
// frontend/ 는 trailingSlash 정적 내보내기라 `/jobs/` 가 `jobs/index.html` 로 저장된다.
// S3(OAC) 원본은 폴더 기본 문서를 찾아 주지 않으므로 경로를 index.html 로 바꿔 준다.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith("/")) {
    request.uri = uri + "index.html";
  } else if (uri.split("/").pop().indexOf(".") === -1) {
    request.uri = uri + "/index.html";
  }
  return request;
}
