;;; package --- vcs-resolve.el
;;; Commentary:
;;; 11 December 2016

;;; Code:

(defcustom vcs-resolve-exe "vcs-resolve" "Executable for vcs-resolve." :group 'local)

;;;###autoload
(defun vcs-resolve-dwim ()
  "Try to guess the best way to run `vcs-resolve`."
  (interactive)
  (cond
   ((region-active-p)
    (vcs-resolve-region))
   (t
    (vcs-resolve-at-point))))

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
  (cond ((eq major-mode 'dired-mode)
         (vcs-resolve--exec (concat (dired-current-directory) (or (thing-at-point 'filename) ""))))
        ((string-match (rx bos (>= 6 (any "A-Fa-f0-9")) eos) (or (thing-at-point 'word) ""))
         (vcs-resolve--exec (thing-at-point 'word)))
        (t
         (vcs-resolve-buffer))))

(defun vcs-resolve--exec (what)
  "Execute `vcs-resolve WHAT` and copy return string to kill ring."
  (let* ((out (shell-command-to-string (format "%s '%s'" vcs-resolve-exe what)))
         (url (car (split-string out))))
    (kill-new url)
    (message "%s" url)))

(provide 'vcs-resolve)
;;; vcs-resolve.el ends here
