/**
 * POSTリクエストにも対応するためのエンドポイント
 */
function doPost(e) {
  // POSTデータの取得
  var params = {};
  if (e.postData && e.postData.type === 'application/json') {
    try {
      params = JSON.parse(e.postData.contents);
    } catch (err) {
      return createErrorResponse('JSONのパースに失敗しました: ' + err.message);
    }
  } else if (e.parameter) {
    params = e.parameter;
  }

  // doGetと同じロジックを流用
  var inputText = params.text;
  var fromLanguage = params.from || 'ja';
  var toLanguage = params.to || 'en';

  if (!inputText) {
    return createErrorResponse("'text' パラメータがありません。");
  }
  if (!isValidLanguageCode(fromLanguage) || !isValidLanguageCode(toLanguage)) {
    return createErrorResponse("無効な言語コードです。'from' と 'to' は有効な ISO 639-1 コードである必要があります。");
  }
  try {
    var translatedText = translateText(inputText, fromLanguage, toLanguage);
    var result = {
      input: inputText,
      from: fromLanguage,
      to: toLanguage,
      translation: translatedText
    };
    return createJsonResponse(result);
  } catch (error) {
    return createErrorResponse(error.message);
  }
}
/**
 * ローマ字から日本語に変換するWeb API。
 * 1. クエリパラメータからテキストを取得
 * 2. 日本語(ローマ字) -> 英語 -> 日本語 の順に翻訳
 */
function doGet(e) {
  // クエリパラメータからテキストを取得
  var inputText = e.parameter.text;
  var fromLanguage = e.parameter.from || 'ja'; // デフォルトは日本語
  var toLanguage = e.parameter.to || 'en';   // デフォルトは英語

  // テキストがない場合はエラーメッセージを表示
  if (!inputText) {
    return createErrorResponse("'text' パラメータがありません。");
  }

  // 言語コードが不正な場合はエラーメッセージを表示
  if (!isValidLanguageCode(fromLanguage) || !isValidLanguageCode(toLanguage)) {
    return createErrorResponse("無効な言語コードです。'from' と 'to' は有効な ISO 639-1 コードである必要があります。");
  }

  // 翻訳処理
  try {
    var translatedText = translateText(inputText, fromLanguage, toLanguage);
    var result = {
      input: inputText,
      from: fromLanguage,
      to: toLanguage,
      translation: translatedText
    };
    return createJsonResponse(result);
  } catch (error) {
    return createErrorResponse(error.message);
  }
}

/**
 * テキストを指定された言語間で翻訳する。
 * @param {string} text 翻訳するテキスト
 * @param {string} sourceLanguageCode 翻訳元の言語コード (ISO 639-1)
 * @param {string} targetLanguageCode 翻訳先の言語コード (ISO 639-1)
 * @returns {string} 翻訳されたテキスト
 */
function translateText(text, sourceLanguageCode, targetLanguageCode) {
  try {
    return LanguageApp.translate(text, sourceLanguageCode, targetLanguageCode);
  } catch (e) {
    // API制限を超えた場合などのエラー処理
    Logger.log("翻訳エラー: " + e.message);
    throw new Error("翻訳中にエラーが発生しました: " + e.message);
  }
}

/**
 * JSON形式のレスポンスを作成するヘルパー関数
 * @param {object} data レスポンスデータ
 * @returns {GoogleAppsScript.Content.TextOutput} JSONレスポンス
 */
function createJsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * エラーレスポンスを作成するヘルパー関数
 * @param {string} errorMessage エラーメッセージ
 * @returns {GoogleAppsScript.Content.TextOutput} JSON形式のエラーレスポンス
 */
function createErrorResponse(errorMessage) {
  return ContentService.createTextOutput(JSON.stringify({ error: errorMessage }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * 有効な言語コードかどうかをチェックするヘルパー関数。
 * 簡単なチェックで、より厳密なチェックが必要な場合は拡張してください。
 * @param {string} languageCode 言語コード (ISO 639-1)
 * @returns {boolean} 有効な言語コードの場合はtrue、そうでない場合はfalse
 */
function isValidLanguageCode(languageCode) {
  // 簡単なチェック: 2文字の文字列で、アルファベットのみ
  return typeof languageCode === 'string' && /^[a-z]{2}$/.test(languageCode);
}


/**
 * テスト関数
 */
function test() {
  var testCases = [
    { romaji: "watashi ha ashita tomodachi to eiga wo mi ni ikimasu", expected: "私は明日友達と映画を見に行きます" },
    { romaji: "kono resutoran ha totemo oishii ryouri ga takusan arimasu", expected: "このレストランはとても美味しい料理がたくさんあります" },
    { romaji: "tenki ga ii node, soto de asobimashou", expected: "天気が良いので、外で遊びましょう" },
    { romaji: "nihonryouri", expected: "日本料理" },
    { romaji: "kagakugijutsu", expected: "科学技術" },
    { romaji: "shinkansen", expected: "新幹線" },
    { romaji: "kirakira", expected: "きらきら" },
    { romaji: "fuwafuwa", expected: "ふわふわ" },
    { romaji: "dokidoki", expected: "ドキドキ" },
    { romaji: "konnichiwa", expected: "こんにちは" },
    { romaji: "yoroshiku onegaishimasu", expected: "よろしくお願いします" },
    { romaji: "yamadatarou", expected: "山田太郎" },
    { romaji: "toukyouto", expected: "東京都" },
    { romaji: "fujisan", expected: "富士山" },
    { romaji: "konpyu-ta-", expected: "コンピュータ" },
    { romaji: "terebi", expected: "テレビ" },
    { romaji: "resutoran", expected: "レストラン" },
    { romaji: "intanetto", expected: "インターネット" },
    { romaji: "hashi", expected: "橋" },  // 箸 / 橋 / 端
    { romaji: "kami", expected: "紙" },  //紙/神/髪
    { romaji: "ame", expected: "雨" }   //雨/飴
  ];

  // WebアプリのURL (提供されたURLを使用)
  var webAppUrl = "https://script.google.com/macros/s/AKfycbxPh_IjkSYpkfxHoGXVzK4oNQ2Vy0uRByGeNGA6ti3M7flAMCYkeJKuoBrALNCMImEi_g/exec";

  testCases.forEach(function(testCase) {
    var romaji = testCase.romaji;
    var expected = testCase.expected;
    // APIエンドポイントにリクエストを送信
    var url = webAppUrl + '?from=en&to=ja&text=' + encodeURIComponent(romaji);
    var response = UrlFetchApp.fetch(url);
    var json = JSON.parse(response.getContentText());
    var result = json.translation;

    Logger.log("-----\nローマ字: " + romaji + "\n期待される結果: " + expected + "\nAPIの結果: " + result);

    // 簡単なアサーション (テストが成功したかどうかを確認)
    if (result === expected) {
      Logger.log("テスト成功!");
    } else {
      Logger.log("テスト失敗! 結果が一致しません。");
    }
  });
}