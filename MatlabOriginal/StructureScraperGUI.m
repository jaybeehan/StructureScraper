function StructureScraperGUI
% StructureScraperGUI v2026-03-03_prettyCopySave_v2
% Fixes pretty-printer assignment error by using cell array lines.
% Right panel shows pretty XML; Copy/Save use pretty XML too.
%
% Regex: lookahead avoids matching <Structures>. [web:117][web:62]

VERSION = "v2026-03-03_prettyCopySave_v2";

fig = uifigure('Name',"Structure Scraper " + VERSION,'Position',[100 100 1340 740]);

btnPick = uibutton(fig,'push', ...
    'Text','Select folder and scrape *.xml', ...
    'Position',[20 700 260 28], ...
    'ButtonPushedFcn',@onPickFolder);

lblFolder = uilabel(fig,'Text','Folder: (none selected)', ...
    'Position',[300 700 1020 28], 'Interpreter','none');

uilabel(fig,'Text','Search Structure ID (partial match):', ...
    'Position',[20 660 300 22]);

edtSearch = uieditfield(fig,'text', ...
    'Position',[20 635 380 26], ...
    'ValueChangedFcn',@onSearchChanged);

chkCase = uicheckbox(fig,'Text','Case-sensitive', ...
    'Position',[420 638 150 22], ...
    'Value',false, ...
    'ValueChangedFcn',@onSearchChanged);

uilabel(fig,'Text','Matches:', 'Position',[20 600 120 22]);

lstMatches = uilistbox(fig, ...
    'Position',[20 170 640 430], ...
    'ValueChangedFcn',@onMatchSelected);

btnCopy = uibutton(fig,'push', ...
    'Text','Copy selected block (pretty)', ...
    'Position',[20 130 300 28], ...
    'Enable','off', ...
    'ButtonPushedFcn',@onCopySelected);

btnSave = uibutton(fig,'push', ...
    'Text','Save selected block (pretty)...', ...
    'Position',[340 130 320 28], ...
    'Enable','off', ...
    'ButtonPushedFcn',@onSaveSelected);

uilabel(fig,'Text','Selected <Structure> block (pretty):', ...
    'Position',[690 700 420 22]);

txtBlock = uitextarea(fig, ...
    'Position',[690 130 630 570], ...
    'Editable','off', ...
    'FontName','Courier New');

lblStatus = uilabel(fig, ...
    'Text',"Status (" + VERSION + "): idle", ...
    'Position',[20 50 1300 22], ...
    'Interpreter','none');

app = struct();
app.structs = repmat(struct('id',"",'name',"",'previewID',"",'block',"",'file',"",'indexInFile',NaN),0,1);
app.filteredIdx = [];
app.selectedPretty = "";
fig.UserData = app;

logStatus("Status (" + VERSION + "): idle");

    function logStatus(msg)
        lblStatus.Text = msg;
        fprintf('%s\n', msg);
        drawnow;
    end

    function onPickFolder(~,~)
        folder = uigetdir(pwd,'Select folder containing the XML files');
        if isequal(folder,0), return; end
        lblFolder.Text = ['Folder: ' folder];

        files = dir(fullfile(folder,'*.xml'));
        if isempty(files)
            resetUIEmpty("Status (" + VERSION + "): no *.xml files found.");
            return;
        end

        allStructs = repmat(struct('id',"",'name',"",'previewID',"",'block',"",'file',"",'indexInFile',NaN),0,1);
        filesWithStructs = 0;

        logStatus("Status (" + VERSION + "): scraping " + numel(files) + " files...");

        for k = 1:numel(files)
            fpath = fullfile(files(k).folder, files(k).name);
            txt = fileread(fpath);

            dbgCount = numel(strfind(txt,'<Structure'));
            previewID = parsePreviewID_forgiving(txt);

            blocks = regexp(txt, '<Structure(?=\s|>)[\s\S]*?</Structure>', 'match'); % [web:117][web:62]

            if ~isempty(blocks), filesWithStructs = filesWithStructs + 1; end

            for i = 1:numel(blocks)
                xmlBlock = string(blocks{i});
                sid = extractAttr(xmlBlock, "ID");
                sname = extractAttr(xmlBlock, "Name");

                allStructs(end+1,1) = struct( ...
                    'id',sid, ...
                    'name',sname, ...
                    'previewID',previewID, ...
                    'block',xmlBlock, ...
                    'file',string(fpath), ...
                    'indexInFile',i); %#ok<AGROW>
            end

            logStatus("Status (" + VERSION + "): " + string(files(k).name) + ...
                " | dbg '<Structure'=" + dbgCount + ...
                " | Preview=" + previewID + ...
                " | structures=" + numel(blocks));
        end

        fig.UserData.structs = allStructs;
        fig.UserData.selectedPretty = "";
        edtSearch.Value = "";
        applyFilterAndUpdateList();

        logStatus("Status (" + VERSION + "): scraped " + numel(allStructs) + ...
            " structures from " + filesWithStructs + " of " + numel(files) + " files.");
    end

    function previewID = parsePreviewID_forgiving(txt)
        previewID = "";
        tok = regexp(txt, '<Preview[\s\S]*?ID="([^"]+)"', 'tokens', 'once'); % [web:62]
        if ~isempty(tok), previewID = string(tok{1}); end
    end

    function val = extractAttr(xmlBlock, attrName)
        val = "";
        openTag = regexp(xmlBlock, '^<Structure[^>]*>', 'match', 'once');
        if isempty(openTag), return; end
        tok = regexp(openTag, attrName + '="([^"]*)"', 'tokens', 'once');
        if ~isempty(tok), val = string(tok{1}); end
    end

    function onSearchChanged(~,~)
        applyFilterAndUpdateList();
    end

    function onMatchSelected(~,~)
        appLocal = fig.UserData;

        if isempty(appLocal.filteredIdx) || isempty(lstMatches.Items) || isempty(lstMatches.Value)
            txtBlock.Value = {''};
            btnCopy.Enable = 'off';
            btnSave.Enable = 'off';
            fig.UserData.selectedPretty = "";
            return;
        end

        sel = string(lstMatches.Value);
        matchPos = find(string(lstMatches.Items) == sel, 1, 'first');
        if isempty(matchPos), return; end
        realIdx = appLocal.filteredIdx(matchPos);

        raw = appLocal.structs(realIdx).block;
        pretty = prettyXmlFragment(raw, 2);

        fig.UserData.selectedPretty = pretty;

        if strlength(pretty) == 0
            txtBlock.Value = {"(Pretty output was empty)"; "Raw begins:"; char(raw(1:min(200,strlength(raw))))};
            fprintf("DBG: pretty output empty for %s\n", sel);
        else
            txtBlock.Value = splitlines(char(pretty));
        end

        btnCopy.Enable = 'on';
        btnSave.Enable = 'on';
    end

    function onCopySelected(~,~)
        pretty = fig.UserData.selectedPretty;
        if strlength(pretty) == 0, return; end
        clipboard('copy', char(pretty));
        logStatus("Status (" + VERSION + "): copied selected block (pretty).");
    end

    function onSaveSelected(~,~)
        pretty = fig.UserData.selectedPretty;
        if strlength(pretty) == 0, return; end

        appLocal = fig.UserData;
        if isempty(appLocal.filteredIdx) || isempty(lstMatches.Value), return; end
        sel = string(lstMatches.Value);
        matchPos = find(string(lstMatches.Items) == sel, 1, 'first');
        if isempty(matchPos), return; end
        realIdx = appLocal.filteredIdx(matchPos);

        s = appLocal.structs(realIdx);
        defaultName = "Structure_" + safeFilePart(s.id) + "_" + safeFilePart(s.previewID) + "_" + realIdx + ".xml";

        [file, path] = uiputfile({'*.xml','XML (*.xml)';'*.txt','Text (*.txt)';'*.*','All Files (*.*)'}, ...
            'Save pretty structure block as', char(defaultName));
        if isequal(file,0), return; end
        outPath = fullfile(path,file);

        fid = fopen(outPath,'w');
        fwrite(fid, char(pretty), 'char');
        fclose(fid);

        logStatus("Status (" + VERSION + "): saved pretty block to " + string(outPath));
    end

    function applyFilterAndUpdateList()
        appLocal = fig.UserData;
        structs = appLocal.structs;

        if isempty(structs)
            lstMatches.Items = {};
            txtBlock.Value = {''};
            btnCopy.Enable = 'off';
            btnSave.Enable = 'off';
            fig.UserData.filteredIdx = [];
            fig.UserData.selectedPretty = "";
            return;
        end

        q = string(edtSearch.Value);
        caseSensitive = chkCase.Value;

        ids = string({structs.id});
        previewIDs = string({structs.previewID});

        if strlength(q) == 0
            keep = true(numel(structs),1);
        else
            if caseSensitive, keep = contains(ids, q);
            else, keep = contains(lower(ids), lower(q));
            end
        end

        filtIdx = find(keep);
        fig.UserData.filteredIdx = filtIdx;

        if isempty(filtIdx)
            lstMatches.Items = {'(no matches)'};
            lstMatches.Value = '(no matches)';
            txtBlock.Value = {''};
            btnCopy.Enable = 'off';
            btnSave.Enable = 'off';
            fig.UserData.selectedPretty = "";
            return;
        end

        display = strings(numel(filtIdx),1);
        for j = 1:numel(filtIdx)
            i = filtIdx(j);
            pv = previewIDs(i);
            if strlength(pv) == 0, pv = "UNKNOWN_PREVIEW"; end
            display(j) = ids(i) + " - " + pv;
        end

        lstMatches.Items = cellstr(display);
        lstMatches.Value = lstMatches.Items{1};
        onMatchSelected();
    end

    function pretty = prettyXmlFragment(xml, indentSpaces)
        s = char(xml);
        if isempty(s), pretty = ""; return; end

        s = regexprep(s, '\r\n|\r', '\n');
        s = regexprep(s, '>\s*<', sprintf('>\n<'));

        parts = regexp(s, '\n', 'split');

        indent = 0;
        out = {};  % cell array of char rows (robust)

        for k = 1:numel(parts)
            line = strtrim(parts{k});
            if isempty(line)
                continue
            end

            isClose = startsWith(line, '</');
            isDecl  = startsWith(line, '<?') || startsWith(line, '<!');
            isSelf  = endsWith(line, '/>') || (~isClose && contains(line, '</'));

            if isClose
                indent = max(indent-1, 0);
            end

            pad = repmat(' ', 1, indentSpaces * indent);
            out{end+1,1} = [pad line]; %#ok<AGROW>

            isOpenOnly = startsWith(line, '<') && ~isClose && ~isDecl && ~isSelf;
            if isOpenOnly
                indent = indent + 1;
            end
        end

        pretty = string(strjoin(out, newline));
    end

    function resetUIEmpty(statusMsg)
        fig.UserData.structs = repmat(struct('id',"",'name',"",'previewID',"",'block',"",'file',"",'indexInFile',NaN),0,1);
        fig.UserData.filteredIdx = [];
        fig.UserData.selectedPretty = "";
        lstMatches.Items = {};
        txtBlock.Value = {''};
        btnCopy.Enable = 'off';
        btnSave.Enable = 'off';
        logStatus(statusMsg);
    end

    function out = safeFilePart(in)
        out = regexprep(string(in), '[^\w\-]+', '_');
        if strlength(out) == 0, out = "NA"; end
    end
end
