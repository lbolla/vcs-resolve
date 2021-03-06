;;; package --- vcs-resolve.el
;;; Commentary:
;;; 11 December 2016

;;; Code:

(defcustom vcs-resolve-exe "vcs-resolve" "Executable for vcs-resolve." :group 'local)

;;;###autoload
(defun vcs-resolve-buffer ()
  "Run `vcs-resolve` on current buffer."
  (interactive)
  (vcs-resolve--exec (or (buffer-file-name) default-directory)))

;;;###autoload
(defun vcs-resolve-region ()
  "Run `vcs-resolve` on current region."
  (interactive)
  (let ((uri (concat
              (buffer-file-name)
              ":"
              (number-to-string (line-number-at-pos (region-beginning)))
              ","
              (number-to-string (- (line-number-at-pos (region-end)) 1)))))
    (message uri)
    (vcs-resolve--exec uri)))

;;;###autoload
(defun vcs-resolve-at-point ()
  "Run `vcs-resolve` on word at point."
  (interactive)
  (vcs-resolve--exec (thing-at-point 'word)))

(defun vcs-resolve--exec (what)
  "Execute `vcs-resolve WHAT` and copy return string to kill ring."
  (let* ((out (shell-command-to-string (concat vcs-resolve-exe " " what)))
         (url (car (split-string out))))
    (kill-new url)
    (message url)))

(provide 'vcs-resolve)
;;; vcs-resolve.el ends here
